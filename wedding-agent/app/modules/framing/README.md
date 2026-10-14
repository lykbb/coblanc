# 摄影师模块交付

对外接口保持 `frame(state: WeddingState) -> dict`，从 `__init__.py` 导出。
接入小组原有 Python 3.11 + LangGraph 流程，内部调用下载后裁剪、修改的 Pi v1.2.0 源码，见相邻的 `pi-wedding/`。
本地项目是小组后端代码快照，来源提交为 `72c87fc928baeed91c9a7518457a253103aed56e`；
没有复制前端。交付时只需把本模块补丁应用到小组的完整仓库。

## 运行方式

在小组仓库的 `wedding-agent/` 执行：

```bash
uv sync --frozen
cd ../pi-wedding
npm ci --ignore-scripts
npm run check
npm run test:unit
cd ../wedding-agent
uv run pytest app/modules/framing
uv run pytest tests/test_contracts.py
```

真实 Pi 运行需要 Node.js 22.19 或更新版本，`node` 必须在 PATH 中。
fake 模式沿用小组的模板方案，不调用模型，也不要求 Node。

摄影师模型尚未选定，所以交付默认保持 fake。选择支持工具/结构化输出的模型后，
在小组现有 `.env` 中设置 `LLM_MODEL_AGENT`、`LLM_API_KEY`、`LLM_BASE_URL`，
并设置 `REAL_MODULES=framing`。所有模型仍通过 `get_llm("agent")` 获取。

## Pi 和 Python 的分工

- Pi 只注册 `search_assets`，只允许 pose/background；每次调用启动独立进程。
- Python 用 LangChain `with_structured_output(Decision)` 生成结构化决策。
- Pi 执行工具并把结果反馈给模型，最终由 Python 检查姿态和参考图是否确实来自资产库。
- 工具上限读 `settings.max_agent_steps`，模型超时读 `settings.llm_timeout_seconds`。
- Node 不接收模型密钥、原始合照或图片二进制，也不注册终端、文件编辑等工具。

## 拍摄与对话规则

只读取需求单、look、摄影师自己的 answers、相关 retouch_plan 和框架轮次。
只写 shot；需要提问时另返回 questions/step_text。主 Agent 负责最终生图 prompt。

默认 `keep_original`，不附姿态参考图。明确更换姿态时，使用资产库登记的编号：

| 身高差 | 档位 | 姿态编号示例 |
| --- | --- | --- |
| ≤ 5 cm | close | close_a |
| > 5 且 ≤ 15 cm | medium | medium_a |
| > 15 cm | large | large_a |

缺少身高、找不到资产或参考图无法保留时，回退到原姿态。镜头描述始终写明实际身高关系。
真实模式最多两轮确认互动、光线、场景、季节、关系；修图阶段不再问用户。

成功输出示例：

```json
{
  "shot": {
    "text": "两人身高 175cm 和 162cm，保持这个身高差和体型；平视半身构图、柔和侧光。",
    "pose": "keep_original",
    "references": []
  }
}
```

失败抛 `ModuleError("GENERATION_FAILED", 中文提示)`，不返回半成品、不修改输入 state。

## 验证和待接入事项

已验证原有测试、Pi 真实进程配合模拟 LangChain 模型的素材检索、身高档边界、
原姿态回退、修图不追问和输入不被修改。

小组当前 `assets/templates/catalog.json` 为空，真实三档姿态素材仍需资产库同学补齐；
本模块不会把测试中的占位图片登记成正式素材。摄影师真实模型、真人照片质量和调用时延
尚未进行付费联调。默认原图姿态的 fake 全流程可运行。

Pi 官方源码固定于 v1.2.0，在 `pi-wedding/` 本地运行，没有 Pi npm SDK 依赖。
运行依赖仅 `typebox@1.3.27`；开发检查依赖为锁定版本的 TypeScript、Biome 和 Node 类型。
没有新增 Python 依赖。
官方项目：[Pi](https://github.com/earendil-works/pi)。

## 源码版目录要求

将 `pi-wedding/` 放在 `wedding-agent/` 旁边，两个模块的 `pi_runtime.mjs` 直接加载
`pi-wedding/packages/wedding/src/cli.ts`。摄影师实现为 `PhotographerAgent`，生图实现为
`GenerationAgent`，它们继承裁剪后本地 Pi 的 Agent；源文件、改动和移除清单见
`pi-wedding/README.md`、`FORK_CHANGES.md`、`UPSTREAM.json`。原有 LangGraph 主图和 Python
接口不变。旧模块的 Pi npm SDK 依赖和锁文件已移除；无需在模块内分别安装 Node 依赖。
