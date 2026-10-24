# 模型配置

Remote API 和本地 Ollama 是两种平等的模型来源。选择时考虑数据流、费用、安装成本、本机资源、网络和服务商并发限制。

## Remote API

需要配置服务 endpoint、model，以及服务商要求的 API key。图片会上传到远程服务，可能产生调用费用。

支持的 Remote 模型使用严格 JSON Schema 输出；Responses 使用 `text.format`，Chat
Completions 使用 `response_format`。GPT-6.1 Sol 默认使用低推理强度、`store=false`、
自动图片细节，并省略采样参数和输出 token 上限。已在模型目录声明
`explicit_prompt_cache` 的模型会使用 30 分钟显式 Prompt Cache；自定义 endpoint 不会
自动假定支持该扩展。

Remote 默认并发为 10，可用 CLI 的 `--concurrency` 覆盖。请求会遵循有效的
`Retry-After`，否则使用有限指数退避；提交状态未知的请求不会盲目重放。详细 JSON
运行记录中会保留 response ID、client request ID、provider status、usage、HTTP status
和白名单限流 headers，但不会记录认证信息、Prompt 或图片内容。

## 本地 Ollama

需要先安装 Ollama 和兼容视觉模型。Moodtag 会检查服务是否可连接，以及已安装模型是否明确支持 vision；不会自动下载模型，也不会在本地失败时切换到远程。

Ollama 的 CLI 请求并发和服务端实际并行能力可能不同，实际排队和速度由本机资源与 Ollama 配置决定。

详细协议、采样参数、运行时诊断和 Ollama Cloud 控制见维护者文档与 [benchmarks.md](benchmarks.md)。
