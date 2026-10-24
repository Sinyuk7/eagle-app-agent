# 模型配置

Remote API 和本地 Ollama 是两种平等的模型来源。选择时考虑数据流、费用、安装成本、本机资源、网络和服务商并发限制。

## Remote API

需要配置服务 endpoint、model，以及服务商要求的 API key。图片会上传到远程服务，可能产生调用费用。

## 本地 Ollama

需要先安装 Ollama 和兼容视觉模型。Moodtag 会检查服务是否可连接，以及已安装模型是否明确支持 vision；不会自动下载模型，也不会在本地失败时切换到远程。

Ollama 的 CLI 请求并发和服务端实际并行能力可能不同，实际排队和速度由本机资源与 Ollama 配置决定。

详细协议、采样参数、运行时诊断和 Ollama Cloud 控制见维护者文档与 [benchmarks.md](benchmarks.md)。
