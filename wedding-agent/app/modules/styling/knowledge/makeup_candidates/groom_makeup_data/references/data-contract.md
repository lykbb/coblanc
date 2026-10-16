# 妆容数据契约 0.2

沿用婚纱数据的 catalog → 分类路由 → recipe/shots/assets 结构。case_id 直接沿用 FMAKEUP/MMAKEUP 编号，不占用 SET/IMG 编号段。独立单图使用 case_unit=single_independent_reference，不伪造组内一致性。

recipe.observations 为 observed，证据必须指向同一案例真实图片；visual_confidence 仅衡量可见细节把握，不表示来源真实性。style_core_hypotheses 为 inferred 且仅单案例；creative_variables 为 proposed。within_session_locks 约束本次确认后的方案一致性，不固定所有用户的五官、色彩或造型。

来源身份、AI 与否及真实化妆步骤分别记录，未知为 null/unverified。production_ready=false 与 generation_tested=false 不可因结构校验通过而修改。文件哈希一致仅证明所取文件与索引一致，不证明图像实拍。

shots 只记录观察视角、遮挡及妆效可见性，不将摄影背景或动作当作妆容要求。assets 中 cloud_file 为预览页，service_url=null 不可拼接成下载链接。source-record 为原索引选中条目摘录，不代表其他条目已审阅。

固定入口不包含图片字节；只按需取指定图。准确妆容色值、产品、色号、原始提示词与模型参数未知时不得编造。生成草稿未运行，不能作为当前产品 compose 模板直接填充。

## 本批新增状态
- 56 个单图案例（新娘28、新郎28），其中2个已批准实验案例原有特征内容保留。批准数据提取不证明来源或生成效果。
- source_truth_status=ai_label_recorded 是原索引曾明确记载 AI 标识，不能因清洗去字改成真人；hold_ai_label 默认不检索。unverified 是证据不足，不等于确认为 AI。
- default_retrieval_eligible=true 只允许进入本批数据审阅检索，retrieval_scope=review_only，不等于 production_ready 或自动生成许可。
- assets.package_file 以外部图片交接包根目录解析（不是本仓库目录），service_url 保持 null 直到图片服务实际绑定。其余 cases 内文件链接以案例目录解析。
- 本轮查看原文件制成的联系表，不能据其确认微小纹理。两份旧实验内容保留原先原图检查的证据描述。
- 56 张文件哈希均与来源索引吻合；哈希证明文件对应，不证明真实性。旧清洗记录原样保留，本轮没有再次去字或修改照片。
