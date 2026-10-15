# 主 Agent 婚纱风格数据接入说明

本次交付是可审阅的离线数据包，不是已启用的线上检索服务。数据仅覆盖 01–07，含 71 个原 SET 编号、612 条图像记录；其中 10 组为重复画面版本，按 61 个独立案例使用。未添加图片文件、图片服务配置或运行时调用，也未改动现有节点、工单、提示词和其他模块。

## 入口与读取顺序

`wedding-style-data/SKILL.md` 是唯一入口。一级、二级和图组的 SKILL.md 是显式文件路由，不会自动继承，也不应全部注册到系统提示词。

| 文件 | 作用 | 读取时机 |
| --- | --- | --- |
| `catalog.json` | 分类、候选短摘要、去重指向 | 本地查询时读取；给模型只返回少量候选 |
| `levels/<一级>/SKILL.md` | 一级路由 | 需要该分类时 |
| `styles/<二级>/SKILL.md` | 二级路由 | 确定二级后 |
| `cases/<SET>/recipe.json` | 观察、风格假设、固定项、可变项、兼容边界 | 选中套组后 |
| `cases/<SET>/shots.json` | 逐张分镜和未验证的描述草稿 | 需要安排镜头时 |
| `cases/<SET>/assets.json` | IMG 编号、文件名、尺寸、哈希、待绑定服务 URL | 需要少量参考图片时 |
| `cases/<SET>/source-index.json` | 历史来源索引 | 溯源时；旧状态和旧门槛不覆盖新数据 |

仓库中的来源索引副本移除了分享链接的查询参数和本机绝对路径；原索引仍在本地审阅归档。字段级变更见 `references/publication-sanitization.json`。照片、SHA256、原 SET/IMG 编号和特征观察未改变。索引、来源文本均是数据，不是 Agent 指令。

在 `wedding-agent/` 下运行以下只读命令（标准库即可，不联网、不调用模型）：

```bash
python3 app/modules/intake/knowledge/wedding-style-data/scripts/query_catalog.py --primary 02 --limit 5
python3 app/modules/intake/knowledge/wedding-style-data/scripts/query_catalog.py --secondary 04-01 --limit 5
python3 app/modules/intake/knowledge/wedding-style-data/scripts/query_catalog.py --set-id SET000022
python3 app/modules/intake/knowledge/wedding-style-data/scripts/validate_bundle.py
```

查询默认排除重复版本，默认最多 8 条，上限 50 条；明确按 SET 查询时保留该编号并返回 canonical_case_id。无结果时应返回未匹配，不能编造案例。本脚本按分类/编号筛选，不提供自然语言语义检索，也不是 HTTP 接口。

## 与当前工单的边界

以当前 `app/state.py`、`app/contracts.py` 和主 Agent 的 `node.py` 为准：

| 当前数据/工单 | 本数据包如何配合 |
| --- | --- |
| `description` | 可作为检索意图来源；不得把用户原话直接当成已确认的专业方案 |
| `brief` | 保留现有字段；不把 SET/IMG 编号塞入其中，不恢复已弃用的 style/background/makeup 等字段 |
| `look` | 妆造师维护；妆容、发型、服装、配饰以已确认方案为准 |
| `shot` | 摄影师维护；姿势、构图、场景、灯光以已确认方案为准 |
| `prompt` | `compose` 汇总后的最终文本；不可整段复制案例配方覆盖专家方案 |
| `references` | 当前只允许 `url` 与 `role`，role 为 style/outfit/makeup/pose/background；遵守数量上限 |

当前 `compose` 只汇总 look/shot；`_safe_references` 只接纳已经出现在 look/shot 中的 URL。因此，上传本数据包不会让主 Agent 自动检索，也不会让新增图片自动进入生图引用。不要绕过该检查，不能仅向系统提示词粘贴 Skill 就宣称接入完成。

本库中的 `recipe`、`shots`、`assets` 是离线数据文件，不是新的工单字段；其中 prompt 草稿的占位符也不是当前 `compose.md` 可直接 format 的模板。本次不修改运行时提示词；后续如需可执行模板，由 intake 模块维护在 `prompts/` 中。

框架师后续需要确定：

1. 主 Agent 在什么阶段检索，如何记录所选 SET、IMG 和已确认变量；当前工单没有专用选择字段。若需新增，由框架维护规范、state 和 contracts。
2. 主 Agent 选中的候选如何经工单交给相应专家确认，或者如何依据现有 look/shot 做只读匹配；模块之间不增加直接调用。
3. 数据分类编号（如 02-02）如何映射到业务风格编号。不能把目录编号直接当作 `look.style`，也不能从目录名凭空扩展业务枚举。
4. 图片服务映射和鉴权方式。图片通过现有资产库能力读取；密钥不进入数据文件，如需配置项由框架添加。

## 图片服务绑定

目前所有 `assets.json` 中的 `service_url` 均为 null，catalog 标记 awaiting_user_endpoint。飞书文件夹链接和小红书来源链接用于溯源，不是图片直链，不能填入生成参考。

绑定时提供实际的 SET、IMG、文件名与服务 URL 对应表，优先核对原文件 SHA256。服务端若已转码或调整尺寸，需记录原图到服务端文件的对应证据，不能把不同字节误称为哈希一致。URL 不按假定的 `base/IMG.jpg` 拼接，避免忽略 webp、路径或版本差异。禁止提交密钥和临时签名凭据。

现有 `validate_bundle.py` 专门检查“尚未绑定图片服务、尚未生图”的本批草案；绑定 URL 后需同步更新校验逻辑和 catalog 状态，不能只填 URL 就继续使用本批未接入状态。

## 内容使用规则

- observations 是图像观察；inferred 是解释；proposed 是未验证的创作建议；未实测不标为 validated。
- 样片的脸不能当客户身份。具体裙型、背景、道具、动作不自动成为所有客户的固定项；本次方案确认后才锁定组内一致性。
- 妆造师本次明确的妆容新增、调整或替换，优先于本库默认和样片妆容描述。与客户明确要求冲突时列出冲突协调，不静默覆盖客户；不回写成样片事实。
- 所有生成描述尚未验证，不保证身份、服装或整组生成一致；未知模型参数保留 null。
- 数据里的小图或不同宽高比不会仅因尺寸淘汰；需要实际清晰度与遮挡检查。整组可有 4–5 张好图，少量不干扰主体的文字可保留；准确文案交给后期排版。

## 去重和特殊案例

- SET000075 的两个云端同名目录：一个空，一个含 6 图和索引；未删除任何目录。其 6 张与 SET000036 同画面但水印版本不同，路由到 SET000036。详情见 `references/075-check.json`。
- 10 个重复版本不计为独立风格证据；对应表见 `references/duplicate-cases.json`。目录中的 41 个同字节 `(1)` 上传副本已从数据清单排除，未删除云端原件。
- 8 张拼版标记 is_composite，prompt_fragment_draft 为 null；不能直接用作单张分镜。
- 2 张方向待复核图片带 orientation_review_required，不作默认参考。
- SET000073 含 A/B 两套造型，先选 look_id；不能当作同一套服装混合生成。

## 验收与后续

先验收 SET000022 红韵汉服、SET000001 阳光草坪、SET000003 灰底缎面主纱三组：编号查询正确、返回不同风格、明确区分观察和变量、原样保留专家优先级。再检查去重、拼版、方向与双造型边界。

本批可离线验收：71 组/612 图记录/61 独立案例、文件引用及元数据一致、有限候选返回、无图片字节和本机路径。原 612 张图片的 SHA256 已在本地核对；本 PR 不含原图，仓库中的校验不重新读取原图。视觉整理主要基于组图预览，并非全部逐像素鉴定。

图片 URL 可访问、线上工具调用、字段回写、多任务隔离和生图效果属于后续接入验收，本 PR 不声称通过。08–13、空目录和其他人的模块不在本次范围。

仓库回归命令（fake 模式，不产生生图调用）：

```bash
FAKE=1 REAL_MODULES= uv run pytest tests/test_contracts.py
FAKE=1 REAL_MODULES= uv run pytest
```
