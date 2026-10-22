## Context

Moodtag 当前已有统一的 `MoodtagAnalysis`、Editorial/default 双 profile、资源化 system/user prompt、taxonomy 归一化和本机 Eagle 写入；`VisionClient` 只覆盖 OpenAI-compatible Chat/Responses。首页 catalog 将 GPT 服务列为主流配置，当前配置只有 `base_url + model`，无法表达本地/云端来源。

本次本机实验使用 Ollama 0.40.8、`qwen3.5:9b`，`/api/show` 返回 MLX runner、vision/thinking capability、声明的 context capacity 262144（不代表请求实际使用 262144 的 num_ctx），以及模型默认 `temperature=1, top_k=20, top_p=0.95, min_p=0, presence_penalty=1.5, repeat_penalty=1`。测试的 16 张图片均正常结束并通过临时 JSON Schema，但这些调用使用临时通用提示词，没有使用 Moodtag 现有 prompt、editorial taxonomy 或业务字段模板。因此，这批数据只是 provider/结构化链路 smoke baseline，不能视作产品提示词质量基线，也不能把其输出当成已标注真值。

Smoke 结果暴露出可转成具体实验假设的问题：低信息图片被泛化描述；可见文字/标识可能诱发过度地点或品牌推断；材质表面观感被写成确定材料；通用 tags 不符合 Moodtag taxonomy；不确定项表达随样本变化。下一轮必须以真实 Moodtag payload 为基线，并有人工标注参考答案。

官方依据：Ollama Structured Outputs 文档支持 `/api/chat` 的 `format` JSON Schema，并建议 temperature 0 提高确定性；Ollama Vision 文档规定 REST 图片使用 base64 `images`；Chat API 定义 `think` 以及模型定义的 thinking 参数；Qwen3.5-9B 官方模型卡建议 instruct/non-thinking 通用任务采样值为 temperature 0.7、top_p 0.8、top_k 20、min_p 0、presence_penalty 1.5。结构化 extraction 的低温建议与 Qwen 通用 instruct 建议目标不同，必须对照评测。当前 MLX runner 的 `/api/show` 参数值用于识别默认基线，不据此推定不同 runner 或不同版本表现相同。

参考资料：[Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)、[Ollama Vision](https://docs.ollama.com/capabilities/vision)、[Ollama Chat API](https://docs.ollama.com/api/chat)、[Ollama Thinking](https://docs.ollama.com/capabilities/thinking)、[Ollama Modelfile parameter reference](https://docs.ollama.com/modelfile)、[Qwen3.5-9B official model card and sampling guidance](https://huggingface.co/Qwen/Qwen3.5-9B)。官方建议用于定义实验候选项，不当作目标任务上的最佳参数结论。

## Goals / Non-Goals

**Goals:**

- 把 Ollama 设置为新用户和首页模型选择中的主要推荐，同时明确保留云端与自定义 OpenAI-compatible 服务。
- 对接 Ollama 原生多模态与 JSON Schema API，复用统一业务结果和本机 Eagle 写入。
- 用测试证据持续优化 system prompt、profile user prompt、字段模板/schema、taxonomy、annotation assembler 和推理参数；每次改动都要报告对质量指标的影响。
- 建立可重复、离线可评估的时尚/服饰图片 benchmark，避免依靠“JSON 合法”作为唯一质量指标。
- 把模型、运行器、Ollama 版本、prompt/schema/taxonomy 版本、参数和图像样本记录到不含图像/密钥的评估报告。

**Non-Goals:**

- 第一阶段不增加常驻本地 HTTP 枢纽或 GUI；本机 CLI 直接调用 Ollama 和 Eagle。
- 不自动将本地失败请求转发云端，不将图片或原始模型输出写入日志。
- 不在没有基准数据的前提下承诺材质、品牌、人物身份等语义准确率。
- 不让模型决定最终 Eagle 字段串；标签归一化和注释组装仍由应用负责。

## Decisions

### 1. Local-first model source, existing adapters remain

模型配置改为带稳定 ID 的 named profile：`source`（ollama/openai-compatible）、显示名称、endpoint、model、protocol（远程协议）、可选 secret reference、profile 默认值。新安装的推荐配置为 Ollama；配置向导先显示“本机图片处理”并探测 loopback。云端/自定义仍可用，但执行确认必须清楚提示图片会离开本机。Ollama local 请求不要求 API key。Loopback 只证明 Moodtag 请求发往本机，不证明推理一定在本机：Ollama 支持 cloud-backed 模型。local-only profile 除 loopback 外，还必须排除被识别为 cloud/remote 的模型；使用模型元数据和请求/响应中可用的 remote_model、remote_host 信号拒绝 remote，不能仅凭模型名判断。无法确认 locality 时显示 unknown，并拒绝宣称 local-only。可指导用户启用 OLLAMA_NO_CLOUD=1 或 server.json disable_ollama_cloud，但这是用户管理的服务端设置，Moodtag 不得假称已强制或验证。

替代方案：在当前单 endpoint 上只允许把 URL 改成 localhost。拒绝它，因为协议形状、凭证需求、模型发现、数据流提示和默认选择已不再由 URL 一项决定；显式 source 可以校验和展示这些差异。

### 2. Native Ollama adapter, common analysis contract

新增 Ollama provider 发送 `/api/chat`：`messages` 用 system/user 文本，用户消息 `images` 传 base64；`format` 传从当前 Moodtag output contract/schema 构建的 JSON Schema；`stream=false`。根据 `/api/tags` 发现安装模型和 capabilities；根据 `/api/show` 读取选中模型的 thinking/default 参数。调用后同时检查 `done=true`、正常 `done_reason`、非空 content、JSON Schema 和 `parse_analysis_response` 业务校验，再转为 `MoodtagAnalysis`。

schema 约束结构而不替代 prompt 和业务验证。schema 应限制枚举/字段/数组边界，但不要为满足 schema 强迫模型编造低置信度内容。若现有“所有自然语言字段必须非空”会迫使低信息图产生 filler，则在 benchmark 中同时比较可空/显式未评估值及确定性 assembler 补值的变体，再选择不破坏 Eagle 注释语义的契约。

替代方案：调用 Ollama 的 `/v1/chat/completions`。拒绝作为主路径，因为它抽象掉原生 `format` schema 和 `think` 控制；仍可单独验证，但不需要另造一套结果合同。

### 3. Prompt and parameter optimization is a measured product loop

评测 pipeline 分成冻结输入与金标、单变量实验、结果评审、发布和回归。每轮只改变一类因素，先测真实现有 Editorial payload；随后分别比较 system prompt、Editorial user prompt、字段定义/JSON 模板、taxonomy subset/说明、Schema 强度、temperature/think/top_p 等，最后才做已验证改动的组合实验。prompt profile 和 taxonomy 资源使用版本号或 git commit 标识。

首轮先比较完整 Preset（组合之间的差异不能归因于单个参数）：A. 实验 smoke 参数 `temperature=0, think=false`；B. Qwen 官方 instruct 通用建议映射到 Ollama 名称 `temperature=0.7, top_p=0.8, top_k=20, min_p=0, presence_penalty=1.5, repeat_penalty=1`（Qwen 文档称 `repetition_penalty`）；C. 当前 Ollama MLX `/api/show` 默认 `temperature=1, top_p=0.95, top_k=20, min_p=0, presence_penalty=1.5, repeat_penalty=1`。选出候选 preset 后，再围绕它一次只变更一个参数，分别比较 temperature、thinking、top_p、presence_penalty 等。Qwen 模型卡提醒推理框架对采样参数的支持可能不同，需验证当前 Ollama 接受和应用的参数。所有设置显式发送/记录，不依赖隐式默认。Qwen 卡片的通用参数不是结构化服装标注的已验证最优值，最终选择以样本集结果为准。

缺陷类别至少包括：泛化/空话、物体或服装误识别、材质/品牌/地点无证据推断、视觉属性遗漏、taxonomy 越界/错类、重复近义标签、中英混杂、字段与用途价值低、Schema/解析失败、截断、延迟。定量指标包括 schema/contract pass rate、brief 有效性、可见属性 precision/recall、unsupported claim rate、tag precision/recall/F1、taxonomy reject/duplicate rate、字段可用率及 latency。Gold 分开标注客观可观察事实（颜色、衣物、物体、姿态、可读文字）与允许的 Editorial 描述（风格方向、视觉 hook、参考价值）；主观描述接受多个合理表达，不做逐字匹配。16 张可作固定核心回归集，但不足以支撑强统计或稳定 p95 承诺；报告样本量和不确定性。人工对固定 gold set 评分，参数实验可多 seed 重复；语义 judge 只用于排序和筛查，不能单独批准 prompt。

替代方案：只测 Schema 合法率，或只用另一个 LLM 评判输出。拒绝，因为前者无法看到本轮已暴露的语义缺陷，后者容易共享同类识别偏差；以人工 gold、规则指标和盲评为主，模型评审仅辅助。

### 4. Benchmark uses consented local images and explicit labels

基准从用户指定的 16 张实测图开始，但现有输出不作为 gold。维护者为每张图标注事实清单、可接受同义表述、不可推断属性、taxonomy tags 和关键描述字段；增加无人物商品图、细节图、模糊/低信息图、带可读文字/标志、室内外/截图等边界样本。评测只用本机 Ollama，不上传图片。样本 manifest 可含 repo 内测试 ID、dimension/sha256 和用途，不提交私有图片；报告只保留 ID、版本、指标和人工观察。

### 5. Optimized schema and templates must match annotation assembly

schema、prompt 的 JSON 示例和 `MoodtagAnalysis`/annotation assembler 从同一份字段定义派生，降低三处漂移。改字段前检查 `ANNOTATION_FIELDS`、`COMMERCIAL_LIST_FIELDS`、`has_analysis_annotation` 和旧注释读写兼容；像“uncertain”这样的辅助评测字段不得未经业务设计直接加进 Eagle 注释。tags 使用 taxonomy 规范 ID，描述字段负责像素证据；不能让模型重复生成 taxonomy 词来填充自然语言字段。

### 6. Default recommendation and data-flow labels

首页 readiness 显示 Ollama 本地状态和推荐模型；本机发现结果优先，不要求填 API key。首次使用可给出安装/拉取指引，但不自动下载 7GB 模型。单次 CLI 分析任务开始时执行一次服务 preflight：先请求配置的 loopback `/api/version`；若服务不可达且确认是 macOS，尝试 `open -j -a Ollama` 唤起已安装应用，并用有上限的间隔轮询等待 API ready。服务 ready 后再发现/校验模型，然后继续用户原请求；模型加载由 Ollama 在首次 `/api/chat` 时完成。若 Ollama.app 不存在、启动命令失败或轮询超时，给出明确手动安装/启动指引。不得自动安装 Ollama、执行 `ollama pull`、切换云端或在任务结束时关闭服务。已运行服务直接复用，不重复启动。云端服务为单独显式选择且在执行摘要中写明远程传图。

### 7. Safe telemetry and bounded execution

记录模型 source/model/version、runner（暂不可得时为 unknown）、Ollama version、prompt/schema/taxonomy revision、sampling options、model_context_capacity（模型声明上限）、requested_num_ctx（本次请求窗口）、num_predict、prompt_eval_count、token counts、done_reason、validator/质量指标、错误类型，以及 Ollama 原生 load_duration、prompt_eval_duration、eval_duration 和 end-to-end latency（duration 字段单位为纳秒，报告注明换算）。首版并发固定为 1 建立串行基线；后续单独测并发及排队。可由客户端总耗时减去可得阶段耗时估算 queue wait，并标为估算值。不得记录 API key、图片字节/base64、prompt 原文、原始 response 或文件完整路径。Provider 验收和语义质量验收分开：前者检查发现、payload、locality guard、done/截断、Schema/解析、错误/重试、无云端回退和 Eagle 写入边界；后者检查 gold set 的事实/Editorial 分层质量、标签和延迟。语义标签不佳不单独判定 adapter 不合格，Provider 通过也不代表语义质量已达标。网络错误和 429/5xx 可有限退避；Schema/语义校验失败只对同一 provider 做一次短修复/重试实验，不做无限循环；是否启用修复重试须基准证明不会让幻觉率上升。

## Risks / Trade-offs

- [Prompt 过长或 taxonomy 塞入过多标签增加 token 和干扰] → 用可比较的 taxonomy facet 子集/短定义实验，记录准确率和延迟，不仅看上下文容量。
- [低温更一致但可能锁定错误答案] → 与 Qwen 官方 instruct 参数及 thinking 选项配对评测；低温不等于事实正确。
- [Schema 强制字段导致 filler] → 对字段可选性及 deterministic post-assembly 做对照；以有效字段率和幻觉率共同选择。
- [评估者偏差/样本过窄] → 建立边界样本、盲评和重复 seed；报告未覆盖范围。
- [loopback 被误当作本地推理证明] → 拒绝未验证的 remote/cloud 模型，locality unknown 时不显示 local-only；说明 Ollama server 的 disable-cloud 选项是额外服务端防护，不是客户端保证。
- [Ollama/MLX 版本行为变化] → 保存每次 live eval 环境元数据，升级 Ollama 或模型 digest 后重跑 gold set。
- [本地模型未安装导致“推荐”不能直接工作] → onboarding 检查模型和磁盘/服务状态，提供用户主动拉取步骤，不暗中下载或切云。
- [Ollama.app 唤起未及时 ready 或系统不允许后台启动] → 有限轮询并提供可复制的手动启动指引；不无限等待、不杀进程、不关闭用户服务。
- [runner 或 runtime 数据字段缺失] → 可选元数据允许 unknown，不阻断配置；报告记录来源与缺项。
- [prompt A/B 改动影响云端 provider] → 第一阶段统一验证业务合同；允许在保持分析合同一致的前提下为本地 provider 使用局部参数策略，避免强迫云端 API 参数相同。

## Migration Plan

1. 添加 benchmark manifest/gold labels、评测脚本和当前真实 Moodtag prompt 的本机基线；保持用户现有设置不动。
2. 以单独配置 profile 引入 Ollama 原生 adapter 和本地模型探测，完成 provider contract 测试。
3. 按实验结果更新 prompt/schema/taxonomy/assembler 和本地参数 preset；所有改动跑 gold set 回归并保留版本对比报告。
4. 将 Ollama 标记为首页推荐和新用户默认来源；老用户现有 endpoint 保持原样，提供显式切换，不在升级时更改数据流。
5. 若新默认出现回归，可通过配置默认来源 feature flag 回退到旧推荐；prompt/schema 改动通过资源版本 revert 回滚。

## Open Questions

- 基准集 gold labels 是否只覆盖 Editorial，还是 Editorial + default 两种 profile 都纳入第一阶段？建议先 Editorial，default 作为第二阶段。
- 语义评估阈值（如 unsupported claim、tag F1）需要第一轮盲评形成基线后确定，不能从 16 个未标注结果虚构阈值。
- Ollama thinking 对视觉标注的收益尚未实测；若提高质量但耗时不可接受，是否将其作为可选“高质量”档位，需依据 benchmark 决定。
