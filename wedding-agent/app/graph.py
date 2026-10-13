"""LangGraph 流程（框架维护）：把 8 个模块串成一条流水线。

小囍接单 →（资料不全）等用户回答 → 小囍接单
        → 妆造师 → 摄影师 → 生图 agent → 质检
质检 →（合格）出预览 → 等用户确认 →（确认）等支付 → 套版 → 小囍揭幕
     →（不合格，未超次数）修图师 → 按修图方案退回妆造师 / 摄影师 / 生图，或换用另一张
     →（超过次数）失败
用户要求重做 → 修图师 → 同上
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.common.config import settings
from app.common.log import current_task
from app.contracts import validate_update
from app.common.progress import STEP_TEXT, store
from app.modules.assets import make_previews, package
from app.modules.framing import frame
from app.modules.generation import generate
from app.modules.intake import intake, reveal
from app.modules.review import check, retouch
from app.modules.styling import style
from app.state import WeddingState


def _module_node(step: str, fn, status: str = "running"):
    """包一层：节点开始时登记进度，检查模块返回值是否符合契约，step_text 同步给前端。"""

    def run(state: WeddingState) -> dict:
        task_id = state["task_id"]
        current_task.set(task_id)
        store.update(task_id, status=status, step=step, step_text=STEP_TEXT[step])
        update = fn(state)
        validate_update(fn.__name__, update)
        if update.get("step_text"):
            store.update(task_id, step_text=update["step_text"])
        return update

    run.__name__ = fn.__name__
    return run


def _rounds(state: WeddingState) -> int:
    return len({item.get("round") for item in state.get("answers", [])})


# ---- 等用户操作的节点：interrupt 暂停，接口收到请求后带着用户的输入继续 ----


def ask_user(state: WeddingState) -> dict:
    round_answers = interrupt({"kind": "questions"})
    next_round = _rounds(state) + 1
    answers = list(state.get("answers", [])) + [{**item, "round": next_round} for item in round_answers]
    return {"answers": answers, "questions": []}


def await_review(state: WeddingState) -> dict:
    decision = interrupt({"kind": "review"})
    if decision["action"] == "confirm":
        return {"best_image_id": decision["image_id"], "user_feedback": None}
    return {"user_feedback": {key: decision.get(key) for key in ("image_id", "reason", "note")}}


def await_payment(state: WeddingState) -> dict:
    interrupt({"kind": "payment"})
    return {}


# ---- 框架自己的小节点 ----


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
    if state.get("questions") and _rounds(state) < settings.max_question_rounds:
        return "ask_user"
    return "styling"


def after_check(state: WeddingState) -> str:
    if state.get("passed"):
        return "make_previews"
    if state.get("retry_count", 0) < settings.max_retouch:
        return "count_retry"
    return "fail"


def after_review(state: WeddingState) -> str:
    return "retouch" if state.get("user_feedback") else "await_payment"


def after_retouch(state: WeddingState) -> str:
    plan = state.get("retouch_plan") or {}
    targets = {"look": "styling", "shot": "framing", "generate": "generate"}
    if plan.get("target") in targets:
        return targets[plan["target"]]
    return "use_other" if plan.get("image_id") else "fail"


def build_graph():
    g = StateGraph(WeddingState)
    g.add_node("intake", _module_node("intake", intake))
    g.add_node("ask_user", ask_user)
    g.add_node("styling", _module_node("styling", style))
    g.add_node("framing", _module_node("framing", frame))
    g.add_node("generate", _module_node("generating", generate))
    g.add_node("check", _module_node("checking", check))
    g.add_node("count_retry", count_retry)
    g.add_node("retouch", _module_node("retouching", retouch))
    g.add_node("use_other", use_other)
    g.add_node("make_previews", _module_node("checking", make_previews))
    g.add_node("await_review", await_review)
    g.add_node("await_payment", await_payment)
    g.add_node("package", _module_node("packaging", package, status="delivering"))
    g.add_node("reveal", _module_node("packaging", reveal, status="delivering"))
    g.add_node("fail", fail)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", after_intake, ["ask_user", "styling"])
    g.add_edge("ask_user", "intake")
    g.add_edge("styling", "framing")
    g.add_edge("framing", "generate")
    g.add_edge("generate", "check")
    g.add_conditional_edges("check", after_check, ["make_previews", "count_retry", "fail"])
    g.add_edge("count_retry", "retouch")
    g.add_conditional_edges("retouch", after_retouch, ["styling", "framing", "generate", "use_other", "fail"])
    g.add_edge("use_other", "make_previews")
    g.add_edge("make_previews", "await_review")
    g.add_conditional_edges("await_review", after_review, ["retouch", "await_payment"])
    g.add_edge("await_payment", "package")
    g.add_edge("package", "reveal")
    g.add_edge("reveal", END)
    g.add_edge("fail", END)
    return g.compile(checkpointer=InMemorySaver())


graph = build_graph()
