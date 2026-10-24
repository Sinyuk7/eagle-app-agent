# Moodboard 工具

Moodboard 是独立于 Eagle 图片打标主流程的素材布局工具。它可以从 Eagle 文件夹生成 catalog、图片规格和几何布局 JSON。

```sh
moodboard layout catalog --folder '<folder-url>' --output catalog.json
moodboard layout inspect --input catalog.json --ids ITEM_ID --output image-specs.json
moodboard layout plan --input catalog.json --ids ITEM_ID_A ITEM_ID_B --mode justified --output layout.json
```

HTML body 设计约束见项目资源中的 `body-design.md`。这些命令不属于普通 `moodtag` 用户流程。
