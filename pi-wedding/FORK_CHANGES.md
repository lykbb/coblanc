# 来源与修改记录

下载：`git clone --depth 1 --branch v1.2.0 https://github.com/earendil-works/pi.git pi-upstream`。
基线：`06a466935536f8c9bcacb2d5efc0fc021be1bdff`。
本地改造目录：`pi-wedding`，本地开发分支 `wedding-agents`。
提交到小组 GitHub 仓库的目录为 `pi-wedding/`，审核分支为 `module/pi-wedding`。

改造保留的原始源码为：

- `packages/agent/src/agent.ts`：状态与生命周期；增加角色约束、工具配置校验、必需适配器及限额。
- `packages/agent/src/agent-loop.ts`：工具循环与并行；增加每轮角色校验、轮次和工具预算。
- `packages/agent/src/types.ts`：循环配置增加角色、预算字段；引用本地消息协议。
- `packages/ai/src/types.ts`：保留消息、工具、事件协议，去除不使用的服务商、模型目录和图片 API 类型。
- `packages/ai/src/utils/event-stream.ts`、`validation.ts`、`text.ts`、`transcript.ts`：保留事件、校验和上下文机制。

新增 `wedding-policy.ts` 和 `packages/wedding/src/` 的两个业务 Agent、JSON 进程通信与 Python 适配器。
两个 Python 模块里的 `pi_runtime.mjs` 现在仅为启动入口，直接加载此源码项目。
旧 Pi npm 依赖和两个模块的 pnpm 锁文件已移除；新依赖在本目录统一锁定。

整个编程 Agent 包已移除，因此其中的文件/终端/目录搜索工具也实际从改造版源码删除。
无关包和它们的测试、构建、发布脚本同步裁剪；这里只运行婚纱照 Agent 的测试，不宣称兼容原 Pi 全部测试。
详细移除路径见 `UPSTREAM.json`；`pi-source.patch` 可在固定基线上重建同一裁剪结果。
