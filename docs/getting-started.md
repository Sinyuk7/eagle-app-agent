# 入门与安装

使用前先打开 Eagle App。Moodtag 连接 Eagle 的本地 API，并按用户选择把图片发送到本地 Ollama 或远程模型服务。

交互首页提供 Eagle 文件夹、当前选区和整个图库三种图片来源。首次标注时按提示配置模型；Remote API 从目录选择模型并自动匹配协议，Ollama 只使用本机已安装的视觉模型。图库范围会先检查 Eagle 返回的总数，超出限制时可添加筛选后重试。非交互环境请通过 `moodtag tag --board <folder> --write`、`moodtag selected --write` 或 `moodtag tag --library --write` 指定范围。

## 安装

正式用户应使用已签名、已公证的 macOS 安装包。Gatekeeper 阻止时，请在系统设置的“隐私与安全性”中确认“仍要打开”。

从 GitHub 安装当前仓库版本：

```sh
uv tool install git+https://github.com/Sinyuk7/eagle-app-agent.git
```

## 第一次运行

```sh
moodtag <folder-url-or-id>
```

Moodtag 会先读取文件夹，再让你选择只处理未描述图片、重新生成全部描述与标签，或退出。直接按 Enter 使用第一项。

高级自动化命令见 [cli-reference.md](cli-reference.md)。
