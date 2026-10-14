"""LangGraph 流程（框架维护）：把 8 个模块串成一条流水线。

小囍接单 ⇄ 用户（小囍以项目经理身份确认风格、规格、物料）
→ 妆造师 ⇄ 用户（展示资产库里的参考图，确认妆容、发型、服饰、配饰）
→ 摄影师 ⇄ 用户（确认两人关系、互动、场景、季节、灯光）
→ 小囍汇总写最终提示词 → 生图 agent → 质检
质检 →（合格）出预览；样片确认后生成 9 张套图并再次出预览，
套图确认 → 等支付 → 套版 → 小囍揭幕
     →（不合格，未超次数）修图师 → 按修图方案退回妆造师 / 摄影师 / 小囍改提示词 / 生图，或换用另一张
     →（超过次数）失败
用户要求重做 → 修图师 → 同上

和用户对话的三位（小囍、妆造师、摄影师）用同一套机制：返回 questions 就暂停等用户回答，
回答后回到自己继续；每人最多问 settings.max_question_rounds 轮；开始生图后不再问用户。
"""

import time

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.common.config import settings
from app.common.log import current_task
from app.common.progress import STEP_TEXT, store
from app.contracts import validate_update
from app.modules.assets import make_previews, package
from app.modules.framing import frame
from app.modules.generation import generate
from app.modules.intake import compose, intake, reveal
from app.modules.review import check, retouch
from app.modules.styling import style
from app.state import WeddingState

ASKERS = {"intake", "style", "frame"}  # 可以和用户对话的对外函数


def _module_node(module: str, step: str, fn, status: str = "running"):
    """包一层：登记进度，检查模块返回值是否符合契约；step_text 只给前端看，不写进工单。"""

    def run(state: WeddingState) -> dict:
        task_id = state["task_id"]
        current_task.set(task_id)
        store.update(task_id, status=status, step=step, step_text=STEP_TEXT[step])
        if settings.fake_delay_seconds and settings.fake_for(module):
            time.sleep(settings.fake_delay_seconds)  # 演示用：让 fake 模式下的进度动画看得见
        update = fn(state)
        validate_update(fn.__name__, update)
        if fn.__name__ in ASKERS:
            update.setdefault("questions", [])  # 没问问题时清掉上一位留下的问题
        step_text = update.pop("step_text", None)
        if step_text:
            store.update(task_id, step_text=step_text)
        return update

    run.__name__ = fn.__name__
    return run


def _rounds(state: WeddingState, asker: str) -> int:
    return (state.get("question_rounds") or {}).get(asker, 0)


def _wants_to_ask(state: WeddingState, asker: str) -> bool:
    return bool(state.get("questions")) and not state.get("candidates") and _rounds(state, asker) < settings.max_question_rounds


def _retouching(state: WeddingState, target: str) -> bool:
    return bool(state.get("candidates")) and (state.get("retouch_plan") or {}).get("target") == target


# ---- 等用户操作的节点：interrupt 暂停，接口收到请求后带着用户的输入继续 ----


def _ask_node(asker: str):
    """谁问的问题，回答就记在谁名下，然后回到谁那里。"""

    def ask(state: WeddingState) -> dict:
        round_answers = interrupt({"kind": "questions"})
        rounds = dict(state.get("question_rounds") or {})
        rounds[asker] = rounds.get(asker, 0) + 1
        answers = list(state.get("answers", [])) + [{**item, "asker": asker, "round": rounds[asker]} for item in round_answers]
        return {"answers": answers, "questions": [], "question_rounds": rounds}

    ask.__name__ = f"ask_{asker}"
    return ask


def await_review(state: WeddingState) -> dict:
    decision = interrupt({"kind": "review"})
    if decision["action"] == "confirm":
        return {"best_image_id": decision["image_id"], "user_feedback": None}
    return {"user_feedback": {key: decision.get(key) for key in ("image_id", "reason", "note")}}


def await_payment(state: WeddingState) -> dict:
    interrupt({"kind": "payment"})
    return {}


# ---- 框架自己的小节点 ----


def prepare_set(state: WeddingState) -> dict:
    """样片确认后切换到套图阶段。

    ``generate`` 仍是唯一负责调用生图服务的模块节点；这里仅在工单上
    标记阶段，下一次调用因此生成 9 张套图。保留累计 total_images，便于
    任务级生图上限和重试计数继续生效。
    """

    generation = dict(state.get("generation") or {})
    generation["stage"] = "set"
    return {"generation": generation}


def count_retry(state: WeddingState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1, "user_feedback": None}


def use_other(state: WeddingState) -> dict:
    return {"best_image_id": state["retouch_plan"]["image_id"], "passed": True}


def fail(state: WeddingState) -> dict:
    store.update(
        state["task_id"],
        status="failed",
        error={"code": "GENERATION_FAILED", "message": "修了几次还是不够像，换一张更清晰的合照再试试吧"},
    )
    return {}


# ---- 路由 ----


def after_intake(state: WeddingState) -> str:
    return "ask_intake" if _wants_to_ask(state, "intake") else "styling"


def after_styling(state: WeddingState) -> str:
    if _wants_to_ask(state, "styling"):
        return "ask_styling"
    return "compose" if _retouching(state, "look") else "framing"  # 修图只改造型时不用再找摄影师


def after_framing(state: WeddingState) -> str:
    return "ask_framing" if _wants_to_ask(state, "framing") else "compose"


def after_check(state: WeddingState) -> str:
    if state.get("passed"):
        return "make_previews"
    if state.get("retry_count", 0) < settings.max_retouch:
        return "count_retry"
    return "fail"


def after_review(state: WeddingState) -> str:
    if state.get("user_feedback"):
        return "retouch"
    # 样片确认后先生成套图；套图预览确认才进入原有支付链路。
    if (state.get("generation") or {}).get("stage") == "sample":
        return "prepare_set"
    return "await_payment"


def after_retouch(state: WeddingState) -> str:
    plan = state.get("retouch_plan") or {}
    targets = {"look": "styling", "shot": "framing", "prompt": "compose", "generate": "generate"}
    if plan.get("target") in targets:
        return targets[plan["target"]]
    return "use_other" if plan.get("image_id") else "fail"


def build_graph():
    g = StateGraph(WeddingState)
    g.add_node("intake", _module_node("intake", "intake", intake))
    g.add_node("ask_intake", _ask_node("intake"))
    g.add_node("styling", _module_node("styling", "styling", style))
    g.add_node("ask_styling", _ask_node("styling"))
    g.add_node("framing", _module_node("framing", "framing", frame))
    g.add_node("ask_framing", _ask_node("framing"))
    g.add_node("compose", _module_node("intake", "composing", compose))
    g.add_node("generate", _module_node("generation", "generating", generate))
    g.add_node("check", _module_node("review", "checking", check))
    g.add_node("count_retry", count_retry)
    g.add_node("retouch", _module_node("review", "retouching", retouch))
    g.add_node("use_other", use_other)
    g.add_node("make_previews", _module_node("assets", "checking", make_previews))
    g.add_node("await_review", await_review)
    g.add_node("prepare_set", prepare_set)
    g.add_node("await_payment", await_payment)
    g.add_node("package", _module_node("assets", "packaging", package, status="delivering"))
    g.add_node("reveal", _module_node("intake", "packaging", reveal, status="delivering"))
    g.add_node("fail", fail)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", after_intake, ["ask_intake", "styling"])
    g.add_edge("ask_intake", "intake")
    g.add_conditional_edges("styling", after_styling, ["ask_styling", "framing", "compose"])
    g.add_edge("ask_styling", "styling")
    g.add_conditional_edges("framing", after_framing, ["ask_framing", "compose"])
    g.add_edge("ask_framing", "framing")
    g.add_edge("compose", "generate")
    g.add_edge("generate", "check")
    g.add_conditional_edges("check", after_check, ["make_previews", "count_retry", "fail"])
    g.add_edge("count_retry", "retouch")
    g.add_conditional_edges("retouch", after_retouch, ["styling", "framing", "compose", "generate", "use_other", "fail"])
    g.add_edge("use_other", "make_previews")
    g.add_edge("make_previews", "await_review")
    g.add_conditional_edges("await_review", after_review, ["retouch", "prepare_set", "await_payment"])
    g.add_edge("prepare_set", "generate")
    g.add_edge("await_payment", "package")
    g.add_edge("package", "reveal")
    g.add_edge("reveal", END)
    g.add_edge("fail", END)
    return g.compile(checkpointer=InMemorySaver())


graph = build_graph()
