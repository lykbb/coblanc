# 主 Agent（小囍）与妆造师修改清单

给负责 `intake` 和 `styling` 的同学及其 AI 编程助手。动手前先读 `AGENTS.md`、`docs/小囍模块接入规范.md`、`docs/小囍接口约定.md`。

## 0. 开始前

1. `git pull origin main`，确认框架更新已经合进来：`app/contracts.py` 里小囍（`intake`）允许写的字段已经包含 `groom_photo_urls`。没有就停下，告诉用户。
2. 从最新的 main 新建分支 `module/intake-styling`，改完提 PR。
3. 只改 `app/modules/intake/` 和 `app/modules/styling/`（含 `prompts/` 和 `test_*.py`）。框架文件、摄影师、生图、修图师、资产库、前端、`docs/`、`tests/` 一律不改；觉得需要改，先停下来问用户。

## 1. 分工线（最重要）

**小囍问"是什么"，专家问"选哪个"，小囍最后只汇总、不改专家的内容。**

| | 问用户什么 | 不能碰 |
| --- | --- | --- |
| 小囍 | 照片、授权、身高、物料、请柬信息 | 风格、妆容、发型、服装、配饰、背景、场景、灯光、姿势 |
| 妆造师 | 风格、一套妆造（新娘和新郎一起） | 场景、灯光、姿势、身高 |
| 摄影师（不是本次任务，仅供参考） | 互动、场景、季节、灯光、姿势 | 妆容、服装 |

## 2. 开始前框架会准备好的（不用你做）

- **补传照片的配套**（要不要补传、换哪几张由小囍决定，见 3.2；框架只管传递和规矩）：用户在对话里补传照片后，框架会在这条回答里附上图片地址 `urls`（框架负责把上传编号换成地址）。小囍可以写 `groom_photo_urls`、`bride_photo_urls`、`photo_urls` 三个照片字段，框架会检查格式和数量（每组 1～10 张）。
- **需求单不再放造型和镜头**：小囍只填 `intent`、`heights_cm`、`body_types`、`keep_features`、`beautify`、`materials`、`invitation`、`missing` 这 8 个字段。`style`、`makeup`、`outfit_bride`、`outfit_groom`、`expression`、`pose`、`background` 这几个字段暂时还留在 `Brief` 里（修图师现在还在读），框架会把它们的默认值改成"还没定"；小囍不再填写，妆造师和摄影师也不要读。专家需要了解用户原话时，读工单里的 `description`。等修图师改完，框架再删掉这几个字段。
- **套系物料的命名**：框架只在规范里写好命名，一套妆造在资产库里的种类是 `look_set`，编号 `look_set_<风格编号>_<名字>`，`tags` 里带风格编号，图片是新娘和新郎同框，另有 `description` 字段写明两人的妆容、发型、服装、配饰；风格物料编号是 `style_<风格编号>`。图片和资产库代码由资产库同学做，**还没做好时** `search_assets("look_set", ...)` 会报错或返回空，妆造师要接住，改用兜底选项，流程照常走。
- **流程测试**：`tests/test_flow.py` 和修图师的流程测试里，检查出场顺序的断言改成"按出场顺序去重"，妆造师问两轮不会让它们失败；`tests/test_flow.py` 里检查需求单 `style` 的断言也会去掉。
- **张数**：先 1 张样片，确认后 9 张套图，随这次框架更新一起合进 main。

## 3. 小囍 `intake()`

### 3.1 提问

- 新郎新娘分组的任务和旧的合照任务**用同一套提问**，删掉现在 `extended` / `LEGACY_QUESTIONS` 两套提问的区分。两种任务只在照片检查时不同。
- 每轮最多 4 个问题。用户在描述里已经说清楚的，不再问。第一轮从下面 4 个里选：

| 题号 | 类型 | 内容 | 要求 |
| --- | --- | --- | --- |
| `q_consent` | single_choice | 照片授权 | 授权已确认时不问；`allow_skip: false`；选项 `standard`「同意：仅用于本次生成，不用于训练，预览带水印，交付后删除原图」和 `keep_photos`「同意，但交付后保留原图」 |
| `q_height` | text | 两人身高大概多少 | 占位「例如 175 / 162」；可跳过 |
| `q_materials` | multi_choice | 需要哪些婚礼物料 | 选项只能是 `invitation` 请柬、`welcome_poster` 迎宾海报、`led_screen` 婚礼大屏（朋友圈图默认都有，不用选）；推荐三个都要 |
| `q_invitation` | text | 请柬上写什么：新人名字、婚礼日期、地点 | 占位「例如 张三 & 李四，2026-12-20，杭州」；可跳过 |

- 不问任何风格、妆造、场景、灯光、姿势的问题。
- 去掉现在的 `q_style` 和按风格决定 `background` 的代码。

### 3.2 照片检查（只在真实模式）

- 只在这三种时候检查，避免重复花钱：第一次调用且授权已确认、刚拿到授权、刚补传了照片。
- 改成**逐张给结果**：`PhotoCheck` 改成列表，每张含序号、人数、是否清晰、是否正脸、是否有遮挡、原因；`prompts/photo_check.md` 同步改成"逐张检查"。分组任务每张应有 1 人，合照任务应有 2 人。
- 不合格时**不要报错**，而是返回补传题（`type: "upload"`，`allow_skip: false`），题号用 `q_groom_photos`（新郎）、`q_bride_photos`（新娘）或 `q_photos`（旧的合照任务），题目里说清是哪张、什么问题，比如「新郎第 2 张有遮挡，请补传一张清晰的正面照」。
- 收到补传后由小囍自己更新照片：从回答的 `urls` 里取新地址，只换掉不合格的那几张（用户传了整组就整组替换），返回完整的新列表。分组任务的 `photo_urls` 必须等于新郎照片加新娘照片。
- 已经问满 `settings.max_question_rounds` 轮还不合格，才抛 `ModuleError("PHOTO_INVALID", 具体原因)`。

### 3.3 需求单

- 只填上面那 8 个字段，造型和镜头的字段不填。保留现在"姓名、日期、地点、身高、要保留的特征只能来自用户原话"的防编造检查。
- `invitation` 来自 `q_invitation` 的回答或用户描述。

### 3.4 写最终提示词 `compose()`

- 开头那句"保持两人五官、身高差和体型不变"由**代码**从 `prompts/opening.md` 读出来放在最前面，不交给大模型写。
- 大模型只负责把妆造师的 `look.text` 和摄影师的 `shot.text` 合成一段通顺的提示词：不增删、不改写专业内容；两边冲突时，姿势和构图按摄影师，服装和妆容按妆造师；不编造。有 `heights_cm` 时写明身高关系。
- 修图补丁（`retouch_plan.target == "prompt"`）只交给大模型改写一次，代码不要再在末尾拼一遍。
- 参考图规则不变：只能用 `look` 和 `shot` 里的，姿势优先，最多 `settings.max_reference_images` 张。

### 3.5 揭幕 `reveal()`

不变。

## 4. 妆造师 `style()`

### 4.1 最多两轮对话，由妆造师自己判断问几轮

| 轮次 | 题号 | 选项来源 | 选项格式 |
| --- | --- | --- | --- |
| 第 1 轮 | `q_style` 选风格 | `search_assets("style")` | `value` 是风格编号（物料编号去掉 `style_` 前缀），`label` 用物料名，`image` 用图片地址 |
| 第 2 轮 | `q_look_set` 选一套妆造 | `search_assets("look_set", [风格编号])`，取 2～3 套 | `value` 是物料编号，`label` 用物料名，`image` 用图片地址 |

- 资产库还没放图、或还不支持 `look_set` 时（报错或返回空），用代码里的兜底文字选项（`image` 为 `None`）。兜底的每一套都要同时写到新娘和新郎。
- 推荐项：用户描述里提到的风格优先，没提到就用第一项。
- 一般按自己的回答决定问哪题（例外见下一条）：没回答 `q_style` 就问 `q_style`；答了 `q_style`、没答 `q_look_set` 就问 `q_look_set`；两题都答了就不问，返回正式版 `look`。跳过也算回答，用推荐项。删掉现在"有任何回答就不再问"的写法。
- 用户描述里已经明确说了风格（比如"想要韩式影棚"），可以跳过第 1 轮，直接问套系。最多问 `settings.max_question_rounds` 轮，超出时框架不会再让它问。
- 每次调用都返回一版 `look`：还在问的时候，按推荐项写草稿。
- 修图阶段（`retouch_plan.target == "look"`，或工单里已有 `candidates`）不问用户，按 `patch` 调整后返回。
- `step_text` 用妆造师的口吻。

### 4.2 输出 `look`

- `text`：新娘和新郎**各自**的妆容、发型、服装、配饰都要写清楚。写作依据是所选套系的 `description` 加风格模板 `prompts/<风格编号>.md`，两者都要读进提示词。
- 必须保留 `keep_features`。`beautify` 不是 `"light"` 时，写明保持真实年龄和五官，不瘦身、不改脸型、不年轻化。
- `style`：风格编号。
- `references`：所选套系图（`role: "outfit"`）加风格图（`role: "style"`）。只能用资产库返回的地址。

### 4.3 提示词文件

- `prompts/agent.md` 只用这些占位符：风格编号、风格模板、套系说明、`keep_features`、`beautify`、修图补丁、用户描述。删掉 `{makeup}`、`{outfit_bride}`、`{outfit_groom}`、`{expression}` 等小囍不再填写的字段。
- 每个风格一个 `prompts/<风格编号>.md`，写清这个风格下新娘和新郎整体的造型方向，不能用 `{makeup}` 这类小囍不再填写的字段做占位符。
- 真实模式：用 `get_llm("agent")`，把 `search_assets` 当工具，最多调用 `settings.max_agent_steps` 次。

## 5. 不要做

- 不做"9 张套图拍成不同镜头"和"挑哪几张照片当身份参考"，这两件框架另定。`compose` 仍然只写一段提示词。
- 不删 fake 分支；fake 模式下不调用任何付费服务。
- 不加新依赖；确实需要先问用户。

## 6. 测试和验收

`uv run pytest tests/test_contracts.py` 和 `uv run pytest` 全部通过，另外新增这些测试：

1. 小囍第一轮的问题只来自 `q_consent`、`q_height`、`q_materials`、`q_invitation`，最多 4 个，不含任何风格、妆造、场景题。
2. 照片检查不合格（用 monkeypatch 模拟视觉结果）时返回补传题而不是报错；补传后照片字段换成了新地址、只换掉不合格的那几张，再检查通过，流程继续。
3. 问满轮数仍不合格时抛 `PHOTO_INVALID`。
4. 同一组照片只检查一次（数一下视觉模型的调用次数）。
5. 妆造师第一次问 `q_style`，第二次问 `q_look_set`，第三次不问，返回正式版 `look`；跳过时用推荐项；描述里已有风格时第一次就直接问 `q_look_set`；资产库不支持 `look_set` 时用兜底选项不报错。
6. `look.text` 同时写到新娘和新郎；`references` 里只有资产库的地址。
7. `compose` 的结果以 `opening.md` 原文开头；修图补丁只出现一次。
8. 全流程顺序仍是小囍 → 妆造师 → 摄影师，`tests/test_flow.py` 不用改就能通过（框架已经把这个检查改成按出场顺序去重）。

PR 说明里写清改了什么、新增了哪些测试、测试结果。
