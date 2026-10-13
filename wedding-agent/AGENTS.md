# 给 AI 编程助手的规则

这是「小囍」AI 婚纱照项目：Python 3.11 + LangGraph + LangChain + FastAPI，前端 Vue 3 + Vite + Vant。
完整规范见 `docs/小囍模块接入规范.md`，接口见 `docs/小囍接口约定.md`。动手前先读这两份。

## 必须遵守

1. 只改用户指定的模块文件夹。不要改 `app/state.py`、`app/graph.py`、`app/runner.py`、`app/contracts.py`、`app/api.py`、`app/common/` 和别人的模块；觉得需要改，先停下来问。
2. 模块之间不直接调用，只通过工单交换数据。唯一例外：`from app.modules.assets import save_image, load_image, search_assets`（妆造师和摄影师把 `search_assets` 当 agent 工具用）。
3. 节点函数写法：`def 函数名(state: WeddingState) -> dict`，必须是普通函数，不能是 `async def`（流程同步运行，async 接不上；要并行就在函数内部用 `concurrent.futures.ThreadPoolExecutor`）。只返回模块卡片里允许写的字段，不修改传进来的 state。
4. 大模型只用 `app.common.llm.get_llm("agent" | "cheap" | "vision")`，代码里不写模型名和密钥；结构化结果用 `with_structured_output`。
5. 密钥和参数从 `app.common.config.settings` 读；新增配置项请用户找框架同学加进 `settings` 和 `.env.example`。
6. 提示词放在模块的 `prompts/` 文件夹，用 .md 文件；占位符用需求单字段名，字面大括号写成 `{{`、`}}`。
7. 用 `settings.fake_for("模块名")` 判断是否返回示例数据；fake 时不调用任何付费服务；不要删掉 fake 分支。
8. 出错抛 `app.common.errors.ModuleError(code, message)`，code 用接口约定里的错误码，message 写给用户看的中文。
9. 付费调用和 agent 循环都要有超时和次数上限，上限从 settings 读。
10. 用户照片只通过资产库存放，不写日志、不上传到项目以外的服务；不用 print，用 `get_logger("<模块文件夹名>")`。
11. 不在模块级变量里存某个任务的数据，多个任务会同时运行。
12. 改完运行 `uv run pytest tests/test_contracts.py` 和 `uv run pytest`，全部通过才算完成；新功能要加测试。
13. 新依赖用 `uv add`，并告诉用户加了什么。

## 命名

- 不能改：模块文件夹名、对外函数名、工单字段名、输出里的键、错误码、`generation/client.py` 的 `generate_image(photo_urls, prompt, seed, references)`、前端 6 个页面组件的 props 和事件名。
- 文件、函数、变量用英文小写加下划线；类每个单词首字母大写；常量全大写加下划线。
- 风格编号（如 `korean_studio`）同时用于需求单 `style`、追问选项 `value`、妆造师 `prompts/<编号>.md`、资产库物料的标签。
- 物料编号 `<种类>_<名字>`，登记在 `app/modules/assets/templates/catalog.json`；姿势编号 `<close|medium|large>_<字母>`，对应物料 `pose_<姿势编号>`；参考图 `role` 只能是 style / outfit / makeup / pose / background；追问编号 `q_<需求单字段>`。
- 输出格式和完整命名表见 `docs/小囍模块接入规范.md` 的「命名与替换规则」，契约代码在 `app/contracts.py`。

## 模块一览

| 模块 | 文件夹 | 函数 | 写入的工单字段 |
|---|---|---|---|
| 主 agent（小囍） | `app/modules/intake/` | `intake`、`compose`、`reveal` | `brief`、`questions`、`prompt`、`references`、`message` |
| 妆造师（agent） | `app/modules/styling/` | `style` | `look` |
| 摄影师（agent） | `app/modules/framing/` | `frame` | `shot` |
| 生图 agent | `app/modules/generation/` | `generate` | `candidates`、`generation` |
| 评测修图师 | `app/modules/review/` | `check`、`retouch` | `scores`、`best_image_id`、`passed`、`retouch_plan` |
| 资产库 | `app/modules/assets/` | `save_image`、`load_image`、`search_assets`、`make_previews`、`package` | `previews`、`deliverables` |

流程：小囍接单 → 妆造师 → 摄影师 → 小囍 `compose` 汇总写最终提示词 → 生图 → 评测修图 → 资产库出预览和套版 → 小囍揭幕。

小囍、妆造师、摄影师都会和用户对话：要问时在返回值里带 `questions` 和 `step_text`（以自己身份说的话），框架暂停等用户回答，把回答记在提问人名下（`answers` 里的 `asker`：intake / styling / framing）后再调用一次。问问题时也要先返回一版主要输出（草稿）；每人最多问 `settings.max_question_rounds` 轮；修图阶段不再问。
| 框架 | `app/` 根目录、`app/common/` | 流程、接口、契约、公共工具 | 进度字段 |
| 前端 | `web/` | 页面 | 只通过 6 个接口通信 |
