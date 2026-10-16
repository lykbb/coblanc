# review 交付：fake 流程、真实模型分支与离线评测

开发分支：`module/review-fix`。仅修改本目录，不新增公共字段、配置或依赖。

真实接入边界、人工评测规则、样本准备与工具命令见 [EVALUATION.md](EVALUATION.md)；人工标注模板见 [sample_annotation_template.json](sample_annotation_template.json)。离线报告和标注字段不改变工单契约。

真实视觉、返工入口及双人向量配对已使用测试替身验证，未调用收费服务。照片到人脸特征的服务等待团队选型，完整真实 check 暂不能运行。诊断与批量工具默认 mock，live 需显式选择并通过授权与配置预检。

## 实现范围

- `check(state)` 返回 `scores`、`best_image_id`、`passed`。两个人脸分数分别达标、身材及手部通过、`issues` 为空时才合格；只在合格候选中按 `total` 推荐最佳图，同分按候选顺序取第一张。
- `retouch(state)` 返回 `retouch_plan`。fake 使用规则判断，真实分支由代码确定方向，get_llm("agent") 只生成修改说明；模型失败时使用相同规则方案。用户反馈优先，按接口已有的 reason 路由。无用户反馈时，可返回 `target=none` 和当前合格的候选编号。
- fake 多种缺陷按脸／手部、身材、造型、指令的顺序处理；真实 agent 只编写具体建议，方向由代码确定，效果仍待真实联调。
- 读已有的 `scores` 用于返工决策，不修改传入工单；retry_count、状态和次数上限继续由框架维护。
- 缺候选、重复图片编号、无效分数、陈旧候选评分、非法反馈都抛 `ModuleError("GENERATION_FAILED", 中文提示)`。
- 保留 `FAKE_FAIL_FIRST_CHECK` 演示：第一次不合格，框架增加 retry_count 后可以通过。
- 真实 check 人脸入口未配置时明确报“尚未接入”，不会偷偷返回 fake 结果或发起视觉付费调用。真实 retouch 有完整评分及模型配置时会调用 agent；开启前应确认预算与服务配置。

视觉通过标记与问题描述矛盾时按问题判为不通过；漏返候选标为无法质检，不影响其他候选。资产读取和人脸比较失败政策仍由框架统一，当前保持原有错误处理。主合照取 `photo_urls[0]`，多余照片暂不读取。

## 运行与复现

在 `wedding-agent/` 项目目录执行：

```bash
uv run pytest app/modules/review
uv run pytest app/modules/review/test_review_flow.py -v
uv run pytest tests/test_contracts.py
uv run pytest
uv run python -m app.modules.review.batch_eval tests/fixtures/after_generation.json
FAKE_FAIL_FIRST_CHECK=1 uv run python -m app.modules.review.batch_eval tests/fixtures/after_generation.json
```

批量入口可接收多份**现有工单格式** JSON。报告包含 case、mode、result 和必要时的 retouch_plan 或 error，这些是报告字段，不是新增工单字段。报告不包含图片、原始工单或照片地址。JSON 读入失败时继续下一份，并以非零退出码结束；质量不合格时输出分数和返工方案，正常结束。

成功例子：after_generation 工单 → `passed=true`、`best_image_id="img_1"`、4 条分数，每条包含两个 face_sim。

质量失败例子：开启 FAKE_FAIL_FIRST_CHECK → `passed=false`、`best_image_id=null`、face_sim 为 `[0.30, 0.81]`、target 为 generate（默认 FACE_SIM_THRESHOLD=0.35，见 docs/样片评分标准.md「线上放行规则」）。

输入失败例子：工单 candidates 为空 → `GENERATION_FAILED`，中文提示“候选图片缺失或格式不正确，请重新生成”。

## 逐条自检

|文档检查项|本轮结果|
|---|---|
|只改自己的模块文件夹|符合，仅 app/modules/review/|
|函数名、参数、普通 def|符合，check(state)、retouch(state)，__init__.py 导出不变|
|只写允许的工单字段|符合，未新增工单字段|
|大模型通过 get_llm，无模型名密钥|符合，视觉和返工均通过统一入口；测试使用模拟模型|
|提示词在 prompts/|符合，vision.md 和 retouch.md|
|fake 跑通、不花钱|模块与流程测试验证；测试禁止访问模型和读图片服务|
|付费调用、agent 循环有上限|模型超时沿用 settings；格式错误最多重试一次；含 SDK 重试的总请求预算不超过 max_agent_steps；人脸服务待接入|
|ModuleError、约定错误码|符合，输入与未接入错误使用 GENERATION_FAILED；批量文件报告使用 FILE_INVALID|
|新配置写 .env.example|不适用，未新增配置或修改公共文件|
|照片不写日志或其他位置|真实分支只从资产库读图，不写图片日志／副本；测试不使用真人照片|
|模块、契约、全量测试|模块 212 项、契约 24 项、全量 282 项全部通过|
|模块验收全部达到|fake 流程和模拟真实响应验证完成；真实照片与人脸服务验收未完成|

## 模拟上传与端到端验证

`test_review_flow.py` 在内存中绘制一张 256×192 的双人几何示意图，通过 FastAPI TestClient 调用现有六个接口，使用临时资产库完成：上传 → 三位角色问答 → 4 张候选与质检 → 返工 → 预览确认 → 模拟支付 → 交付。没有真人照片，不调用付费服务，不操作浏览器或当前正在使用的任务。

7 个流程案例覆盖：face、hands、body、style、other 五种用户返工；第一次质检失败后自动重生成并交付；连续质检失败到达框架上限后停止。交付案例故意确认第二张图，并检查最终 best_image_id 和五种交付文件可访问。返工同时验证原图与回答保留、不再提问、妆造返工保留摄影结果、摄影返工保留妆造结果。

这些测试验证 API、review 与框架集成。生成、视觉评测、水印及套版仍沿用其他模块的 fake／占位实现；双人示意图不能用于验证真实身份相似度。

## 后续需确认

人脸比对服务／模型、双人对应规则、服务获准名单、阈值标定和调用预算。新依赖与配置由框架同学统一添加。本轮不改 tests/photos/；真实照片须本人授权，后续使用资产库存放。当前测试图片是公共测试夹具生成的纯色图，不能证明人脸相似度或视觉检测效果。
