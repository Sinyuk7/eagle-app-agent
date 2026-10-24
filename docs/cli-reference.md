# 高级 CLI 与自动化

普通用户使用 `moodtag <folder>`。以下命令面向 Agent、脚本和维护者。

```sh
moodtag status --board '<folder-id>'
moodtag tag --board '<folder-id>'
moodtag tag --board '<folder-id>' --write
moodtag tag --board '<folder-id>' --write --force
moodtag selected --write
moodtag tag --board '<folder-id>' --tag CELINE --tag editorial
moodtag tag --board '<folder-id>' --rating 4 --shape panoramic-landscape
moodtag tag --tag CELINE --rating 4
moodtag export-context --board '<folder-id>' --output context.md
```

`tag` 默认不写回 Eagle；`--write` 显式启用写回，`--force` 重新处理已有 Moodtag 描述。`--limit`、`--max-board-items`、`--concurrency` 和 `--json` 用于自动化边界与机器输出。

`moodtag selected` 在任务开始时读取 Eagle 当前选区一次；空选区会直接返回，不初始化模型。Folder 仍递归包含子文件夹，除非传入 `--no-recursive`。可重复传入 `--tag`，所有标签都必须匹配（交集）；筛选值是 Eagle 人工元数据，不受 Moodtag Profile Taxonomy 限制。`--rating` 使用 Eagle V2 的 `rating` 整数参数，取值 0–5，按精确评分匹配；Item 返回字段 `star` 映射为内部 rating 元数据。`--shape` 使用 Eagle 原生分类：`square`、`portrait`、`panoramic-portrait`、`landscape`、`panoramic-landscape`。Moodtag 不自行计算 Shape，也不提供 missing/valid/malformed 注释状态筛选参数。

在高级 CLI 中，不带 `--board` 的筛选命令会以整个图库为范围；不带 `--board` 且没有筛选时，使用 `--library` 明确请求整个图库。交互首页提供 Folder、Current selection 和 Entire library 三种范围；只有 Entire library 会询问可选筛选条件。

Scope 查询使用 Eagle 本地 Web API V2（`/api/v2/item/get`）；需要 Eagle 4.0 Build 21 或更新版本。当前验证设备返回 Eagle 4.0.0 Build 20260401；只读查询验证了 `rating=1`、`rating=2` 的精确评分结果，以及已知 Shape 的原生筛选。若 Eagle API 拒绝已请求的过滤条件，会明确报错，不会退回未筛选分析。Shape 分类阈值由 Eagle 决定。

Moodtag 生成的 tags（包括从 `use_intents` 派生的标签）统一按活动 Profile Taxonomy 校验、规范化、去重，并在合并后应用 `max_tags`。Eagle 中已有的人工 tags 不经过该 Taxonomy 过滤，写回会保留它们及人工备注。
