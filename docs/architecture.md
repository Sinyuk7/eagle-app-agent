# 架构说明

Moodtag 由四层组成：

- Eagle client：读取 folder、item metadata、缩略图和写回字段。
- CLI workflow：board-first 摘要、策略选择、模型配置和结果反馈。
- Provider adapters：Remote API 与 Ollama，输出统一的 Moodtag analysis contract。
- Annotation layer：识别 Moodtag 区块、合并 tags、保留人工 annotation。

主流程先扫描 Eagle，再根据策略选择图片；写回前重新获取 item metadata，避免分析期间的人工修改被旧快照覆盖。
