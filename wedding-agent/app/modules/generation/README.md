# 生图模块交付

对外接口仍为 `generate(state: WeddingState) -> dict`；
服务出口仍为 `client.py` 的 `generate_image(photo_urls, prompt, seed, references) -> bytes`。
内部由 `pi-wedding/` 中改过的 Pi 源码调度，Python 线程池并行执行候选任务。
只写 candidates/generation，发送的 prompt 与主 Agent 给出的内容完全一致。

## 安装和演示

在 `wedding-agent/` 执行：

```bash
uv sync --frozen
cd ../pi-wedding
npm ci --ignore-scripts
npm run check
npm run test:unit
cd ../wedding-agent
uv run pytest app/modules/generation
uv run pytest tests/test_contracts.py
uv run pytest
```

真实 Pi 模式需要 Node.js 22.19+，且 `node` 在 PATH 中。
默认 fake 保留原有行为：复制资产库中的合照作为四张示例候选，提供不同 image_id；
这些是流程占位图，不是 AI 生成的婚纱照。

## 方舟 Seedream 主力服务

在小组现有 `.env` 里设置以下已有配置项，密钥只留本地：

```dotenv
FAKE=1
REAL_MODULES=generation
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_API_KEY=
SEEDREAM_MODEL=doubao-seedream-5-0-pro-260628
```

摄影师模型暂未确定时，可以只启用 generation，其余模块保留 fake。
先通过资产库读取合照和参考图，转成 Base64 输入；请求返回 Base64 图片，
由 `save_image` 存回项目资产库，不依赖临时下载链接。
当前产品输入仍是一张双人合照，不声称已实现单人婚照或两张单人照的身份对应。

Seedream 5.0 Pro 一次生成一张，因此四张候选对应四个并行请求。
不传 `seed`、`n`、`negative_prompt` 或 `sequential_image_generation`。
原契约要求候选的 seed 是整数，`seed=-1` 明确表示服务未提供种子；
不把本地随机编号当成模型 seed，不承诺逐像素复现。
审计日志记录服务、模型、有效参数、服务返回的尺寸/用量、请求编号（若有）及结果。
日志不记录照片、图片 Base64 或密钥。

官方接口：[图片生成 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=en)；
[Seedream 5.0 Pro](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)。

## Pi、重试和预算

Pi 只注册 `generate_candidate`，按固定计划发出候选任务，不额外调用语言模型做调度。
Python 保留原图/带参考图工作流选择，以及有限的主备切换和重试。

| 限制 | 使用的现有配置 |
| --- | --- |
| 每轮目标张数 | candidates_per_round，默认 4 |
| 每任务累计候选数 | max_images_per_task，默认 16 |
| 一轮等待上限 | image_timeout_seconds，默认 120 秒 |
| 每张额外重试次数 | max_retouch，默认 2，暂复用现有配置 |
| Pi 工具次数 | max_agent_steps，默认 6 |

如果剩余预算不足以完成目标张数，直接报错；不自动把四张目标降为三张。
每轮服务提交还受剩余候选预算的保守限制，主备调用与重试共享一个线程安全预算。
`generation.total_images` 始终表示累计已产出的候选数量；尝试次数记录在日志里。
HTTP 429/5xx、明确连接失败可重试；鉴权拒绝不重试。
超时导致结果无法确认时，停止自动重新提交，避免重复生成；失败时整轮报错，不隐瞒部分失败。

修图计划不改变 prompt。支持 `size=1K/1.5K/2K/宽x高` 的合法尺寸调整，
其余自然语言修图意见保持 prompt 并重新采样，以标准提示词优化模式执行。
需要改创作要求时应由评测模块把 target 指向 prompt，由主 Agent 改写。

## 可选 RunningHub 备用

备用默认关闭。团队确认使用 RunningHub 后，填现有的 `RUNNINGHUB_API_KEY`、
`RUNNINGHUB_WORKFLOW_ID`，并按自己的 ComfyUI workflow 填 `runninghub_mapping.json`：

```json
{
  "photo_nodes": [{"nodeId": "实际编号", "fieldName": "image"}],
  "reference_nodes": [{"nodeId": "实际编号", "fieldName": "image"}],
  "prompt_node": {"nodeId": "实际编号", "fieldName": "text"},
  "seed_node": {"nodeId": "实际编号", "fieldName": "seed"}
}
```

这些编号必须取自实际工作流，不能使用示例占位值。每个工作流执行只应输出一张图，
必须能保留双人身份，并提供足够的参考图输入节点。
主力出现可重试故障且备用配置完整时才切换；没有配置的备用不会冒充为可用服务。
工作流支持 seed 时记录实际提交值，否则也返回 -1。
备用 API 支持上传、任务创建、状态轮询、取回图片；需要实际工作流和账号才能联调。

官方接口：[RunningHub 工作流执行](https://rhtv.runninghub.cn/runninghub-api-doc-cn/api-425749013)。

## 交付自检

- 固定同步接口、合法返回字段、输入不被修改：通过。
- fake、实际 Pi 进程、四路并发屏障测试、主备策略、重试预算、任务隔离、日志脱敏：通过。
- 小组契约和全流程测试：通过。
- 获得用户确认的资产库兼容修复：`load_image` 可读取 `/templates/`，保留路径检查。
- 未修改工单、LangGraph 主图、runner、契约、公共配置或其他业务模块。
- 未新增 Python 依赖；两个模块共享独立的 Pi 源码项目，依赖在 `pi-wedding/package-lock.json` 锁定。
- 付费真人出图、脸部一致性、正式备用工作流和真实时延：尚未验证。

成功例子为四张含 image_id/url/seed 的候选；未配置真实模型、素材不可读、
预算不足或服务故障都抛接口约定的 ModuleError。完整可运行例子见模块测试。

## 源码版目录要求

将 `pi-wedding/` 放在 `wedding-agent/` 旁边，两个模块的 `pi_runtime.mjs` 直接加载
`pi-wedding/packages/wedding/src/cli.ts`。摄影师实现为 `PhotographerAgent`，生图实现为
`GenerationAgent`，它们继承裁剪后本地 Pi 的 Agent；源文件、改动和移除清单见
`pi-wedding/README.md`、`FORK_CHANGES.md`、`UPSTREAM.json`。原有 LangGraph 主图和 Python
接口不变。旧模块的 Pi npm SDK 依赖和锁文件已移除；无需在模块内分别安装 Node 依赖。
