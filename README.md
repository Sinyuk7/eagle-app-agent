# eagle-app-agent

`eagle-app-agent` 提供 `moodtag` CLI，用来读取 Eagle App 文件夹里的图片，并生成可写回 Eagle 的标签和备注。

## 1. 安装

发布到 PyPI 后，推荐这样安装：

```sh
uv tool install eagle-app-agent
```

确认安装成功：

```sh
moodtag --help
```

如果还没有发布 PyPI，可以临时从 GitHub 安装：

```sh
uv tool install git+https://github.com/Sinyuk7/eagle-app-agent.git
```

使用前请先打开 Eagle App。默认会连接 Eagle 本地 API：

```text
http://localhost:41595
```

模型服务和 API Key 通常由维护者配置。需要本地配置时看 `CONTRIBUTING.md`。

## 2. 找到 Eagle 文件夹 ID

在 Eagle App 左侧文件夹上右键，选择复制链接，会得到类似：

```text
http://localhost:41595/folder?id=MQBUH98ILYTQ0
```

取 `id=` 后面的值作为 `--board`：

```text
MQBUH98ILYTQ0
```

虽然 `--board` 也支持精确文件夹名或路径，但推荐始终使用文件夹 ID，避免重名。

## 3. 执行

先查看文件夹状态：

```sh
moodtag status --board 'MQBUH98ILYTQ0'
```

只读分析，不写入 Eagle：

```sh
moodtag tag --board 'MQBUH98ILYTQ0'
```

确认输出后，写回 Eagle：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --write
```

并发处理图片分析：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --write --concurrency 4
```

导出文件夹上下文为 Markdown：

```sh
moodtag export-context --board 'MQBUH98ILYTQ0' --output context.md
```

为 HTML moodboard 模块准备图片规格或几何计划：

```sh
moodboard layout catalog --folder 'http://localhost:41595/folder?id=MQBUH98ILYTQ0' --output catalog.json
moodboard layout inspect --input catalog.json --ids ITEM_ID_A ITEM_ID_B --output image-specs.json
moodboard layout plan --input catalog.json --ids ITEM_ID_A ITEM_ID_B ITEM_ID_C --mode justified --output layout.json
```

`catalog` 只把 Eagle 文件夹准备成素材池；网页里的某个模块可以用 `--ids`
从素材池里选择 1 张、2 张、3 张或任意张图片。`inspect` 只输出图片
src、原始宽高、比例和可写入 `<img>` 的 `width` / `height` 规格；`plan`
只输出几何 JSON。正文 HTML 结构、横排/竖排/对照/序列/图片墙等语义选择仍由
agent 编写，文件夹 URL 不是布局单位。

## 必要信息

`moodtag tag` 默认是 dry run，不会修改 Eagle。只有加上 `--write` 才会写入。

`moodtag tag --write` 会覆盖被处理图片的 Eagle `tags` 和 `annotation`，不会和原有元数据合并。

`--board` 默认会递归包含所选文件夹和所有子文件夹。所有 board 命令默认最多允许 100 个去重后的图片项；超过会退出，避免误操作大目录。确认要处理大目录时显式提高门禁：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --max-board-items 500 --write
```

只处理当前文件夹、不包含子文件夹时加 `--no-recursive`。

`moodtag tag` 每次都会在终端输出本次 provider plan、每张图片实际命中的 provider/model/host，并默认写入 JSONL 运行日志。日志默认位于 `~/.cache/moodtag/runs`，保留最近 50 个 `moodtag-*.jsonl` 文件。

默认发送给模型的预览图长边是 `768px`。需要更高细节时可以传 `--image-edge 1024`。

只处理一小批图片：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --write --limit 5
```

重新处理已有 Moodtag 输出的图片：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --write --force
```

维护者文档、环境变量、测试和发布检查见 `CONTRIBUTING.md`。
