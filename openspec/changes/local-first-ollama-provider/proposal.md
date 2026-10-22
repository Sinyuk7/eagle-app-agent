## Why

当前 Moodtag 的模型配置与首页 catalog 把云端 API 放在默认位置，而本机 `Ollama 0.40.8 + qwen3.5:9b (MLX)` 已能通过视觉输入和 JSON Schema 完成真实图片分析。将本地 Ollama 设为主要推荐可以减少图片外传，并让主要工作流与用户的本地素材库保持一致，同时保留云端和自定义服务作为明确可选项。

## What Changes

- 将 Ollama 本地模型提升为首页和模型配置流程中的默认推荐，支持从本机服务发现已安装模型并显示连接及视觉能力状态。
- 增加 Ollama 原生 `/api/chat` Provider，通过 `images` 发送图片、`format` 发送 JSON Schema，并验证完成原因、输出结构和 Moodtag 业务合同。
- 建立基于固定本地图片集的提示词与模型参数优化闭环：基线、受控 A/B、缺陷分类、评审、回归；测试结果驱动 system/user prompt、JSON 模板、taxonomy、profile 和推理参数逐轮改进。
- 将本地 Ollama、云端 API、自定义 OpenAI-compatible 服务纳入统一的可命名模型配置；选中配置进入现有 profile、分析、预览和 Eagle 写入流程。
- 在配置和执行摘要中明确图片处理位置；本地选项不得静默回退到云端，云端请求必须清楚提示图片将发送给远程服务。
- 复用 `MoodtagAnalysis`、taxonomy reconciliation、注释组装和 Eagle 本地写入路径；不让模型直接生成 Eagle 写入对象。
- 将现有 Chat/Responses catalog 保留为可选服务，调整模型 catalog 和配置契约以区分服务类型、协议、地址、模型、凭证及默认配置。
- 增加 Ollama 连接探测、超时/有限重试、结构化输出失败诊断和不泄露图片、密钥、prompt 的遥测。
- 添加离线模拟测试和显式 opt-in 的本机 live eval，覆盖本轮 16 张实测素材及新增边界样本；将结构正确率、事实依据、字段可用性、taxonomy 精确率/召回率、重复率和延迟分别量化。

## Capabilities

### New Capabilities

- `local-ollama-provider`: 原生 Ollama 视觉请求、Schema 输出、模型发现、连接检测、错误处理和本地数据流保证。
- `model-source-selection`: 配置本地、云端、自定义来源及命名配置；在使用前展示来源和图片流向，管理默认推荐。
- `analysis-result-review`: 将统一分析结果、标签组和生成注释提供给用户检查，再交由本机 Eagle adapter 写入。
- `prompt-quality-iteration`: 版本化提示词、字段模板、taxonomy 和采样参数，使用标注样本开展受控质量评估并阻止回归。

### Modified Capabilities

<!-- Existing requirements live in active change artifacts rather than openspec/specs; the new capabilities define the target contract. -->

## Impact

- 主要代码：`moodtag_core/provider.py`、`contract.py`、`response.py`、`catalog.py`、`moodtag/config.py`、`moodtag/cli.py` 及 `moodtag/ui/`。
- 资源与文档：model resources、README、CLI setup/help、Eagle 本地写入与数据流说明。
- 测试：provider payload/response、模型发现、配置持久化与密钥隔离、选择流程、TTY 与非 TTY 输出、live eval/report。
- 外部依赖：优先沿用 Python 标准库 HTTP 实现，不强制新增 Ollama SDK；Ollama 服务和模型由用户本机单独安装。
