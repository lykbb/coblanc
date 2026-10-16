# 新娘与新郎妆容候选数据

本目录向妆造师模块提供可按需读取的数据 Skill，覆盖飞书两边的 **01_候选底库**：新娘28、新郎28，共14类56个单张独立案例。保留 FMAKEUP/MMAKEUP 编号，不占婚纱 SET/IMG 段，不把不同人物打成同人同妆套系。

本 PR 仅新增此目录；不改运行时、工单、资产目录或婚纱知识库。没有生图、没有调用模型。原图片不在 Git 中，由牵头人另交完整图片包。

## 入口

- [新娘入口](bride_makeup_data/SKILL.md) → [短摘要索引](bride_makeup_data/catalog.json)
- [新郎入口](groom_makeup_data/SKILL.md) → [短摘要索引](groom_makeup_data/catalog.json)
- [图片服务映射](image_service_manifest.json)：56条原文件哈希、尺寸、外部图片包路径、待填服务地址、案例文件路径。
- [来源与不确定性](source_audit.json)：来源线索及未核实事项。
- [接入说明](integration.md)：框架师剩余工作与验收。
- [离线核验快照](validation_record.json)：图片与源索引哈希检查记录，不代表真实性认证。

层级为入口 → 分类路由 → 单例 SKILL / recipe / shots / assets / source-record。只注册两个主入口或一个检索适配器，按需加载，不把72份 Skill 全文放进系统提示词。

## 审阅状态

- FMAKEUP000040、MMAKEUP000036 是用户已认可的两个实验案例，其原有特征、固定边界和变量保留。
- 其他54项已整理，仍待本轮逐例审阅。
- FMAKEUP000036、FMAKEUP000043 的原索引明确记载 AI/即梦标识。保留记录以追溯，`hold_ai_label` 且 `default_retrieval_eligible=false`，默认检索排除。
- 其余54项的实拍真实性、原作者及完整后期未独立核实。`default_retrieval_eligible=true` 仅代表可在 `review_only` 范围检索，所有案例 `production_ready=false`、`generation_tested=false`。
- 分类名称用于检索，不是所有人的固定妆容模板。客户身份与明确保留特征不变；妆造师本次明确方案优先，和客户要求冲突时协调。

## 本地读取

以下命令从本目录运行，仅返回摘要，不读图片、不联网：

```bash
python3 bride_makeup_data/scripts/query_catalog.py --category 02 --limit 4
python3 groom_makeup_data/scripts/query_catalog.py --id MMAKEUP000036
```

默认列表排除两条 AI 标识记录；显式查其编号时返回原记录及状态，调用方仍须尊重不可默认选用标志。脚本不是已注册的 Agent 工具，也不自动装入资产库。

从 wedding-agent 目录验证：

```bash
uv run pytest app/modules/styling/knowledge/makeup_candidates/test_makeup_data.py
uv run pytest tests/test_contracts.py
uv run pytest
```
