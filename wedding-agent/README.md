# 小囍 · AI 婚纱照

上传双方各 1～10 张生活照，先生成 1 张样片；确认方向后再生成 9 张婚礼照套图和婚礼物料（请柬、迎宾海报、婚礼大屏、朋友圈图）。

- 模块分工和开发规范：`docs/小囍模块接入规范.md`
- 前后端接口：`docs/小囍接口约定.md`
- 给 AI 编程助手看的规则：`AGENTS.md`

## 运行

> 下面的路径是 jing 本机的仓库路径（`ai-wedding-test`），其他人换成自己 clone 下来的仓库路径即可。

下面的命令只在项目文件夹里安装依赖，不装全局包（uv 和 Node 本身除外）。

### 1. 准备工具（只需一次）

macOS 用 Homebrew 安装：

```bash
brew install uv node
```

需要 Node.js 20 以上（`node -v` 查看）。

### 2. 第一次安装依赖

仓库根目录 `ai-wedding/` 里有 `wedding-agent/` 和 `pi-wedding/` 两个文件夹：

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent"
uv sync                      # Python 依赖，装进 wedding-agent/.venv
cd web && npm ci && cd ..    # 前端依赖，装进 web/node_modules
cd ../pi-wedding && npm ci   # Pi 运行时依赖（没有它，8 个 Pi 相关测试会失败）
```

### 3. 配置 .env

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent"
cp .env.example .env
```

用编辑器打开 `wedding-agent/.env`，主要改这几项（**真实 key 只写在 .env 里，不要提交，不要截图发群**）：

| 变量 | 说明 |
|---|---|
| `FAKE` | `1`：默认所有模块用示例数据 |
| `REAL_MODULES` | 用真实实现的模块，逗号分隔，例如 `generation`；填 `none` 表示全部用示例数据 |
| `LLM_API_KEY` | 火山方舟 API Key（Seedream 生图也用这个 key） |
| `SEEDREAM_MODEL` | 生图模型 ID，当前账号用 `doubao-seedream-5-0-flash-260915` |
| `MAX_AGENT_STEPS` | Agent 最多走几步，套图建议 `10` |

| `CHAT_API_KEY` / `CHAT_BASE_URL` / `CHAT_MODEL` | 可选。对话和看图用的模型，任意兼容 OpenAI 接口的服务都行（默认 `https://api.deepseek.com` + `deepseek-flash`；通义千问用 `https://dashscope.aliyuncs.com/compatible-mode/v1` + `qwen-vl-max`）。不填用上面的 `LLM_*`。生图仍用 Seedream。旧名 `DEEPSEEK_*` 仍然有效 |
| `CHAT_MODEL_AGENT` / `_CHEAP` / `_VISION` | 可选，按用途单独指定模型，留空用 `CHAT_MODEL` |

检查大模型能不能连上（只发一句很短的文字，不打印密钥）：

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent"
uv run python -m app.scripts.check_llm          # 检查 agent、cheap、vision 三种
uv run python -m app.scripts.check_llm agent    # 只检查一种
```

### 4. 启动（开两个终端，都不要关）

终端 1，后端：

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent"
uv run uvicorn app.api:app --reload --port 8000
```

终端 2，前端：

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent/web"
npm run dev
```

打开：

- Vue 版前端：http://localhost:5173/
- COBLANC 原型（已接真实接口）：http://localhost:5173/coblanc-film/
- 后端接口说明页：http://127.0.0.1:8000/docs

### 5. 不花钱的测试模式

终端 1 改用下面的命令启动。所有模块都用示例数据，不调用 Seedream：

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent"
REAL_MODULES=none uv run uvicorn app.api:app --reload --port 8000
```

只想看前端、不启动后端：把 `web/.env` 里的 `VITE_USE_MOCK` 设成 `true`。这只对 Vue 版有效，COBLANC 原型必须连后端。

### 6. 跑测试

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent"
uv run pytest                          # 全部后端测试
uv run pytest app/modules/styling      # 只跑某个模块
uv run pytest tests/test_contracts.py  # 检查替换后的模块能不能直接接入
cd web && npm run build                # 前端能否构建
cd ../../pi-wedding && npm run test:unit   # Pi 运行时单元测试
```

### 7. 常见错误

| 现象 | 原因和处理 |
|---|---|
| `ModelNotOpen` | 方舟账号没有开通这个模型。到方舟控制台开通，或把 `SEEDREAM_MODEL` 改成已开通的模型 ID |
| `SetLimitExceeded` | 方舟账号的额度或安全体验限额用完了。在控制台充值或调整限额后重试 |
| 页面一直转圈、超时，或提示「连不上服务」 | 后端或前端的终端被关了。两个终端都要一直开着，重新执行第 4 步 |
| `address already in use` | 8000 或 5173 端口已经有服务在运行。直接用已开的那个，或先关掉旧终端 |
| Pi 相关测试失败 | 没有在 `pi-wedding` 里执行 `npm ci` |

## fake 模式和真实模式

- `.env` 里 `FAKE=1`：所有模块返回示例数据，整条流程不花钱就能跑通。
- 某个模块写好了真实实现，在 `REAL_MODULES` 里写上它的名字（例如 `REAL_MODULES=styling,generation`），其他模块继续用示例数据。
- `FAKE_FAIL_FIRST_CHECK=1`：第一次质检故意不合格，用来演示修图流程。
- `FAKE_DELAY_SECONDS=2`：每个模块停 2 秒，演示时能看清网页上的专家接力动画。

## 目录

```text
app/
  state.py        工单定义
  graph.py        LangGraph 流程
  runner.py       后台跑流程、暂停等用户、继续
  contracts.py    模块接口契约
  api.py          6 个接口
  common/         配置、大模型、错误、日志、进度
  modules/        intake 小囍 · styling 妆造师 · framing 摄影师
                  generation 生图 agent · review 评测修图师 · assets 资产库
web/              前端（Vue 3 + Vite + Vant）
tests/            示例工单、全流程测试、测试照片
docs/             模块规范和接口约定
```

现在每个模块只有 fake 实现，代码里的 `TODO(模块名)` 是各自要补的地方。
