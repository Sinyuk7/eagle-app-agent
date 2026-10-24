# eagle-app-agent

Moodtag 是一个模型来源无关的 Eagle AI 图片整理工具：它读取 Eagle 文件夹中的图片，生成 AI 描述和标签，并把结果写回 Eagle。

## 开始使用

1. 打开 Eagle App。
2. 安装 Moodtag（见[安装说明](docs/getting-started.md)）。
3. 运行：

```sh
moodtag <Eagle 文件夹 URL 或 ID>
```

首次运行会先读取文件夹并显示图片总数、已有 Moodtag 描述、待处理图片和不支持的素材。然后选择：

- 仅处理未生成 AI 描述的图片（直接按 Enter）
- 重新生成 AI 描述与标签
- 退出

退出不会调用模型，也不会修改 Eagle。

## 选择模型来源

如果尚未配置模型，Moodtag 会在你选择处理图片后显示两个平等选项：

- **Remote API**：无需安装本地推理模型，只需配置服务商要求的 endpoint、model 和 API key。可能产生调用费用，图片会上传给服务商。
- **本地 Ollama**：在本机运行，不产生远程模型 API 调用费，但需要安装 Ollama 和视觉模型，并消耗本机 CPU、GPU 和内存。

两种来源都支持图片分析、标签生成、备注写回和批量处理。实际速度取决于模型、硬件、网络、服务商限制和请求规模；本地失败时不会自动把图片发送到远程服务。已有有效配置会直接复用。

完整配置说明见 [model-setup.md](docs/model-setup.md)。

## 已有 Eagle 元数据

Moodtag 会保留人工 tags 和人工备注：

- AI tags 与已有 tags 去重合并。
- 只替换 Moodtag 自己生成的描述区域。
- 人工 tags 和备注不会因为重新生成而被清空。
- 当前版本无法安全区分旧 AI tags 和人工 tags，因此重新生成可能保留旧 AI tags。

普通主流程不需要理解 dry run、`--write` 或 `--force`。Agent、脚本和维护者可以使用高级 `moodtag tag` 接口，详见 [cli-reference.md](docs/cli-reference.md)。

## 安装

Apple Silicon Mac 使用正式发布的签名安装包。若 macOS 阻止打开，请到“系统设置 → 隐私与安全性”查看并选择“仍要打开”。

当前使用 GitHub 安装：具体步骤见 [getting-started.md](docs/getting-started.md)。

## 其他文档

- [入门与安装](docs/getting-started.md)
- [模型配置](docs/model-setup.md)
- [高级 CLI 与自动化](docs/cli-reference.md)
- [架构说明](docs/architecture.md)
- [Benchmark](docs/benchmarks.md)
- [Moodboard 工具](docs/moodboard.md)
- [贡献指南](CONTRIBUTING.md)
