# 高级 CLI 与自动化

普通用户使用 `moodtag <folder>`。以下命令面向 Agent、脚本和维护者。

```sh
moodtag status --board '<folder-id>'
moodtag tag --board '<folder-id>'
moodtag tag --board '<folder-id>' --write
moodtag tag --board '<folder-id>' --write --force
moodtag export-context --board '<folder-id>' --output context.md
```

`tag` 默认不写回 Eagle；`--write` 显式启用写回，`--force` 重新处理已有 Moodtag 描述。`--limit`、`--max-board-items`、`--concurrency` 和 `--json` 用于自动化边界与机器输出。

这些参数不属于普通用户的主流程。写回仍保留人工 tags 和备注的安全合并规则。
