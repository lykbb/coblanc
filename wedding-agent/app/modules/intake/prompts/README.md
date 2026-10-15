# 小囍（主 Agent）的提示词与 skill

- `prompts/dialogue.md`：对话提示词，始终生效。人设、欢迎语、安全规则、流程、需求单（section `brief`）、交付寄语（section `reveal`）。
- `skills/photo_sort/SKILL.md`：看照片 skill。质量检查（section `check`）、分类、参考照、纪念品。
- `skills/image_prompt/SKILL.md`：生图 skill。身份保持开头（section `identity`）、合成提示词（section `compose`）。

代码用 `node.load_section(文件, 名称)` 读取 `<!-- section: 名称 -->` 与 `<!-- /section -->` 之间的内容，不要删掉这些标记。
