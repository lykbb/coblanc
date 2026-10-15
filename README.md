

主项目在 `wedding-agent/`，完整运行步骤见 [wedding-agent/README.md](wedding-agent/README.md#运行)。

快速启动（两个终端）：

```bash
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent "&& uv run uvicorn app.api:app --reload --port 8000
cd "/Users/lyk/AI产品经理/AI小组项目 婚纱照/ai-wedding-test/wedding-agent/web "&& npm run dev
```

然后打开 http://localhost:5173/ 或 http://localhost:5173/coblanc-film/ 。
