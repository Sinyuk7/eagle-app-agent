# eagle-app-agent

`eagle-app-agent` 提供 `moodtag` CLI，用来读取 Eagle App 文件夹里的图片，并生成可写回 Eagle 的标签和备注。

## 1. 主路径

安装完成后，默认 happy path 是一条命令：

```sh
moodtag <board-url-or-id>
```

可接受两种输入：

```text
http://localhost:41595/folder?id=MQBUH98ILYTQ0
MQBUH98ILYTQ0
```

执行时会按这个顺序走：

- 解析并显示目标 Eagle 文件夹
- 显示 scope、item 数量、当前 model、覆盖风险
- 首次缺少完整模型配置时，直接在 CLI 中进入 setup
- 将 endpoint 配置保存到 JSON，将 key 保存到 `~/.config/moodtag/.env`
- 用 `y/N` 明确确认后，才开始真正写回 Eagle

模型 endpoint、protocol、model 和 API key 均需由用户配置；不会注入默认供应商或默认模型。

必要支持面：

```sh
moodtag help
moodtag --help
moodtag config
```

`moodtag config` 会显示当前 effective defaults、`env_file` 路径，以及
API key 是否已就绪。

这是下一版本的全新配置格式。旧的 provider/fallback 字段不参与运行；删除旧配置后，
使用 `moodtag config setup` 重新填写完整 endpoint。

## 2. 安装（Mac Apple Silicon）

在 release 下载 `Moodtag-<version>-macos-arm64.dmg`。双击 DMG，再双击其中的
`.pkg` 并按 macOS 安装器完成安装。安装后打开 Terminal：

```sh
moodtag --help
moodtag <board-url-or-id>
```

安装包自带运行时，使用 `moodtag` 不需要 Python、`uv`、`npm` 或 Homebrew。
当前安装包支持 Apple Silicon Mac（M1-M5）。首次运行主命令时，CLI 会自动引导
API key setup。

如果 macOS 提示无法验证开发者，可在 `.pkg` 上按住 Control 点击，选择“打开”并确认；
也可以到“系统设置 → 隐私与安全性 → 仍要打开”。

开发者或 Intel Mac 可使用 Python 包安装：

```sh
uv tool install eagle-app-agent
```

如果还没有发布 PyPI，可以临时从 GitHub 安装：

```sh
uv tool install git+https://github.com/Sinyuk7/eagle-app-agent.git
```

使用前请先打开 Eagle App。默认会连接 Eagle 本地 API：

```text
http://localhost:41595
```

API Key 不写入 `moodtag config` 的 JSON 文件。可使用环境变量、
`~/.config/moodtag/.env`，或当前目录的 `.env`：

```sh
export MOODTAG_API_KEY='你的模型 API Key'

moodtag config set --protocol responses \
  --base-url https://your-model-service.example/v1 \
  --model your-vision-model
moodtag config auth

moodtag config
```

## 3. 高级命令

主路径之外，现有维护者/高级用户命令仍然保留。

查看文件夹状态：

```sh
moodtag status --board 'MQBUH98ILYTQ0'
```

高级 dry run：

```sh
moodtag tag --board 'MQBUH98ILYTQ0'
```

显式写回：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --write
```

并发处理：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --write --concurrency 4
```

导出上下文：

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

读取 HTML body 设计合同：

```sh
moodboard resources get body-design.md --json
```

`body-design.md` 只把 body-only、可访问性、图片资产、无脚本依赖和响应式稳定作为硬合同。
视觉表达部分是设计维度和反模板检查，不是固定组件清单；视觉叙事、时间线、主视觉、色调、
调色板、镜头语言、动作、空间关系、细节和对比都应按项目材料决定是否出现。素材池较大时，
末尾应保留 final reference audit layer，用来检查参考覆盖、重复、缺口和异常素材；它可以是
Reference wall，也可以是 contact sheet、archive shelf、film strip 或其他适合当前页面的形态。

## 必要信息

`moodtag tag` 默认是 dry run，不会修改 Eagle。只有加上 `--write` 才会写入。

`moodtag tag --write` 会覆盖被处理图片的 Eagle `tags` 和 `annotation`，不会和原有元数据合并。

`--board` 默认会递归包含所选文件夹和所有子文件夹。所有 board 命令默认最多允许 100 个去重后的图片项；超过会退出，避免误操作大目录。确认要处理大目录时显式提高门禁：

```sh
moodtag tag --board 'MQBUH98ILYTQ0' --max-board-items 500 --write
```

只处理当前文件夹、不包含子文件夹时加 `--no-recursive`。

`moodtag tag` 会输出当前 protocol/model/host，并默认写入 JSONL 运行日志。日志默认位于 `~/.cache/moodtag/runs`，保留最近 50 个 `moodtag-*.jsonl` 文件；日志不记录 API key、请求 header、请求 body 或图片 data URL。

开始并发前，`moodtag` 会先串行验证一张可处理图片。若模型 endpoint 返回 `401` 或 `403`，会立即停止本次运行；按提示更新 `MOODTAG_API_KEY` 后再重试。网络错误、429 和 5xx 只重试同一个 endpoint，不会切换服务。视频等非图片素材会显示为 `skip`，不会记为失败。

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
