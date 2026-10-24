## Context

当前响应归一化流程分别处理模型 `tags` 和 `use_intents`。前者经过 `reconcile_tags()`，后者由全局映射直接产生派生标签，再合并进 `MoodtagAnalysis`。两个内置 Profile 目前恰好包含所有派生标签，但这个隐含条件不适合未来增加 Profile。

当前 Eagle 范围主要由 Folder 递归扫描得到。`EagleClient.list_items()` 已负责分页和 Item 解析，但没有统一的选区或条件筛选抽象。新的范围入口必须复用现有分析、三态注释检测和 metadata-safe writeback，并在分析开始时冻结候选集合。

## Goals / Non-Goals

**Goals:**

- 让所有本次 Moodtag 生成的标签统一经过活动 Profile 的 Taxonomy。
- 保持 `use_intents` 作为结构化分析字段独立存在，即使其映射标签不适用于某个 Profile。
- 修正重复合法标签进入 `rejected_tags` 的统计错误。
- 支持 Eagle 当前选区、Folder、人工 Tag 以及经确认的 Rating/Shape 查询。
- 返回去重、稳定排序且包含必要元数据的内部范围快照。
- 在任务开始后固定范围，后续 Eagle 选区变化不影响本次任务。

**Non-Goals:**

- 不扩展 Taxonomy、同义词、Tag Group 管理或自由标签生成。
- 不过滤或重写用户已有的 Eagle tags；Taxonomy 只约束生成 tags。
- 不公开 `missing`、`valid`、`malformed` 作为第一版范围参数。
- 不引入查询 DSL、Smart Folder、数据库或新的分析工作流。
- 不改变模型协议、Prompt、JSON Schema、annotation 格式或写回合并规则。

## Decisions

### 1. 统一生成标签候选的最终校验

先把原始模型 tags 与合法 `use_intents` 的映射目标合并，再调用一次带活动 `taxonomy` 的 reconciliation。最终校验负责大小写规范化、稳定去重、拒绝未知标签和 `max_tags` 截断；随后由同一批 canonical tags 计算 `tag_groups`。

重复的合法候选只忽略，不进入 `rejected_tags`。不合法的 intent 仍记录在 `rejected_use_intents`；如果其映射目标不属于活动 Taxonomy，则不写入生成 tags，但不删除结构化的 `use_intents`。

替代方案：给 `reconcile_use_intents()` 增加独立的 Profile 校验并分别截断。放弃原因：容易让模型 tags 和派生 tags 争抢不同的数量配额，也会再次产生两个校验边界。

### 2. 人工标签与生成标签分离

`MoodtagAnalysis.tags` 表示本次生成的 canonical tags。写回时继续使用已有 metadata-safe 合并：已有 Eagle tags 全部保留，生成 tags 追加并大小写不敏感去重。范围筛选的 `--tag` 只作为 Eagle 查询值，不要求出现在 Moodtag Taxonomy 中。

替代方案：写回前把全部 Eagle tags 重新过滤到 Taxonomy。放弃原因：会删除用户标签，并违反既有安全写回契约。

### 3. ScopeResolver 返回稳定范围快照

新增内部 `ResolvedScope` 概念，至少包含来源标识、去重排序后的 `EagleItem` 列表和总数。Resolver 可以调用 Eagle V2 的服务器筛选；若目标版本不支持所请求条件，必须明确报错，不能静默退化为未筛选查询。

`selected` 在任务开始时只读取一次。Folder 递归规则沿用现有行为。多个筛选条件采用交集语义；多个 `--tag` 的 AND/OR 语义必须在 CLI 契约中明确，第一版采用重复 `--tag` 的 AND 语义。`--rating` 采用精确匹配，除非 Eagle API 目标版本只提供其他明确语义；`--shape` 优先传给 Eagle 原生查询，不用宽高比较冒充 Eagle panoramic 分类。

替代方案：Resolver 只返回 Item IDs，再重新读取全部 Item。放弃原因：会重复请求并丢失扫描统计、注释状态和媒体元数据。

### 4. 分阶段公开范围入口

立即提供 `moodtag selected` 和现有 Folder 范围；条件筛选先公开 `--tag`，在 API 验证后加入 `--rating`、`--shape`。不公开 `--state`，由现有 skip / regenerate WritePolicy 处理 Moodtag 状态。

### 5. API 适配与兼容性

Eagle API Adapter 负责 V2 字段和 CLI 语义之间的映射，例如 Item 的 `star` 与查询参数 `rating`。V2 分页必须基于响应的 total/offset/limit 完整读取，超过单页上限时不得静默截断。V2 不可用或不支持筛选字段时返回可理解的错误；只有明确的兼容路径才允许使用旧接口。

## Risks / Trade-offs

- [Eagle 版本对 `isSelected` 或 Shape 筛选支持不一致] → 在 Adapter 中探测并报告能力，不把未应用的筛选当作成功。
- [用户在分析期间改变选区] → 任务只使用开始时创建的 `ResolvedScope` 快照。
- [多个 Tag 的语义被误解] → 固定为重复 `--tag` 的交集，并添加 CLI/测试文档。
- [派生标签被当前 Profile 拒绝] → 保留 `use_intents` 字段和拒绝信息，只阻止越界标签进入生成 tags。
- [范围查询返回重复或不稳定顺序] → 按 Item ID 去重并使用稳定排序后再展示和处理。
- [范围为空触发无关模型设置] → 空范围直接结束，不初始化模型或调用 AI。

## Eagle API Capability Findings

- Eagle Web API V2 `/api/v2/item/get` accepts POST JSON filters `rating` (integer 0–5) and `shape` (`square`, `portrait`, `panoramic-portrait`, `landscape`, `panoramic-landscape`). `rating` is the query key; returned Item metadata uses `star`.
- Local read-only verification against Eagle 4.0.0 Build 20260401 returned exact matching star values for `rating=1` (225 items) and `rating=2` (4 items). `star=4` left the unfiltered total unchanged, confirming it is not the query key.
- The local `shape=portrait` result contained 13,224 items; its first 1,000 returned items all had portrait dimensions. Eagle owns Shape classification and its numeric thresholds remain undisclosed.
- Unknown/invalid Shape values may return an empty successful response, so CLI enum validation is required. Rating and Shape are passed to Eagle V2 as native filters; Moodtag does not infer or silently drop them.

## Migration Plan

1. 先实现统一标签候选校验和重复合法标签修正，并补充核心回归测试。
2. 抽取 ScopeResolver/ResolvedScope，保持现有 Folder 调用路径行为不变。
3. 添加 selected 和 `--tag`，再根据 Eagle API 验证结果启用 Rating/Shape。
4. 增加分页、快照、空范围、不支持媒体和 API 能力错误测试。
5. 完成 CLI 文档与 OpenSpec 验收后再进入实现。

回滚时可独立撤回 Scope 新入口；标签校验修复和现有 Folder 路径应保持独立提交，便于安全回退。

## Open Questions

- 目标 Eagle 版本对 V2 `isSelected`、`rating`、`shape` 的确切请求字段和错误响应格式是什么？
- `--rating` 是否始终采用精确匹配，还是需要另一个明确命名的最低评分参数？
- `selected` 是否需要兼容没有选中图片时的 JSON 输出契约？
