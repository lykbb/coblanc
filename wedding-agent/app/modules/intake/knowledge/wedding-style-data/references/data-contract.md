# 数据契约 v0.2

沿用实验版的事实、推测、可变项、分镜和来源分离结构。assets改为file_name、sha256、width、height、format、source_page、cloud_folder、service_url；图片不嵌入GitHub数据包。service_url为null时图片服务尚未绑定。不得伪造可读链接。

recipe是组级配方，shots按IMG拆分；observations只保存已观察内容，style_core_hypotheses不自动升级为分类硬规则，creative_variables只标proposed。原source-index保留原貌，其旧门槛、上传状态或误标不覆盖新数据。

优先级：用户明确要求与本次已确认方案；妆造师的最新明确妆容要求优先于本库妆容默认；遇到客户冲突列明协调。身份来源不是样片人物。模型参数未知保持null；generation_tested=false。

案例去重用独立证据标记，不改旧SET/IMG；同图不同水印不当成两个独立样本。一级与二级仅路由、比较与组合，不扩大既有授权范围。
