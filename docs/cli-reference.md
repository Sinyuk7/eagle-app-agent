# CLI 进阶用法

普通使用请先启动 Eagle，再运行 `moodtag` 进入交互首页，或运行 `moodtag <Eagle 文件夹 URL 或 ID>` 处理指定文件夹。

以下命令适合查询或自动化：

```sh
moodtag status --board '<folder-id>'                  # 查看处理状态
moodtag tag --board '<folder-id>'                     # 预览，不写回
moodtag tag --board '<folder-id>' --write             # 分析并写回
moodtag tag --board '<folder-id>' --write --force     # 重新处理已有描述
moodtag config                                         # 配置模型或偏好
```

`tag` 默认不修改 Eagle；只有加上 `--write` 才会写回。`--force` 会重新处理已有 Moodtag 描述。

查看完整命令和选项：

```sh
moodtag --help
```
