## Why

Moodtag 已经具备封闭的专业 Taxonomy 和安全写回流程，但 `use_intents` 派生标签仍可能绕过当前 Profile 的最终校验；同时，用户只能按文件夹启动分析，无法直接处理 Eagle 当前选区或按已有元数据缩小范围。现在补齐这两个边界，可以扩展处理入口而不改变模型协议、Prompt、分析 Schema 或人工标签保留规则。

## What Changes

- 将模型直接生成的 tags 与 `use_intents` 派生标签合并后统一经过当前 Profile 的 Taxonomy、规范化、去重和最终 `max_tags` 限制。
- 修正重复合法标签被错误计入 `rejected_tags` 的问题。
- 保留 Eagle 中已有的人工标签，即使它们不属于 Moodtag Taxonomy；Taxonomy 只约束本次 Moodtag 生成的标签。
- 新增 `moodtag selected`，在任务开始时固定 Eagle 当前选区快照。
- 为已有 Folder 范围增加有限条件筛选，首批支持人工 `--tag`，并评估 `--rating` 与 Eagle 原生 `--shape` 查询语义。
- 让筛选后的范围复用现有 skip / regenerate、分析、预览、媒体类型检查和安全写回流程。
- 用带必要元数据的内部范围快照承载去重、排序和统计结果；筛选条件不得被 Taxonomy 限制。
- 对 Eagle V2 分页、空选区、空筛选结果、不支持媒体和 V2 不可用等情况提供明确行为。
- 暂不公开 Moodtag `missing / valid / malformed` 作为筛选参数；这些状态继续由内部处理策略使用。

## Capabilities

### New Capabilities

- `profile-scoped-tag-contract`: 保证所有 Moodtag 生成标签，包括意图派生标签，都符合当前 Profile 的固定 Taxonomy。
- `eagle-item-scope-resolution`: 从 Eagle 当前选区、文件夹和有限条件筛选构造稳定的 Item 范围快照。

### Modified Capabilities

- <!-- 本次不修改现有主规格；新增能力通过独立规格定义。 -->

## Impact

主要涉及 `moodtag_core/taxonomy.py`、`moodtag_core/response.py`、`moodtag/cli.py` 及相关测试。

外部依赖为 Eagle 本地 Web API V2；需要确认目标 Eagle 版本对 `isSelected`、`tags`、`rating`、`shape` 和分页参数的实际支持。不会引入数据库、查询 DSL、Tag 管理器或新的模型工作流，也不会改变人工 tags 和人工 annotation 的安全写回契约。
