# Moodtag

Moodtag 为 Eagle 图片生成 AI 描述和标签，并将结果写回 Eagle。

## 开始使用

先启动 Eagle，再选择一种方式运行 Moodtag：

```sh
moodtag
```

进入交互首页，按提示选择图片范围并开始处理。也可以直接指定文件夹：

```sh
moodtag <Eagle 文件夹 URL 或 ID>
```

首次使用时，Moodtag 会引导你配置模型。Remote API 会将图片发送给服务商，可能产生费用；Ollama 使用本机安装的视觉模型。

分析结果默认使用英文；将 `export MOODTAG_LANG=""` 添加到 Shell 配置文件可跟随系统语言，设置为 `export MOODTAG_LANG=zh` 或 `export MOODTAG_LANG=en` 可指定语言。

## 如何安装

macOS 用户可从 [GitHub Releases](https://github.com/Sinyuk7/eagle-app-agent/releases/latest) 下载签名安装包。

也可使用 uv 从 GitHub 安装：

```sh
uv tool install git+https://github.com/Sinyuk7/eagle-app-agent.git
```

## 更多

- [模型配置](docs/model-setup.md)
- [CLI 进阶用法](docs/cli-reference.md)
- [贡献指南](CONTRIBUTING.md)
