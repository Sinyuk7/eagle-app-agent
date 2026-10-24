# 入门与安装

使用前先打开 Eagle App。Moodtag 连接 Eagle 的本地 API，并按用户选择把图片发送到本地 Ollama 或远程模型服务。

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
