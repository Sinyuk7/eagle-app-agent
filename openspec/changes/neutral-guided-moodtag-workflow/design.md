## Context

当前主命令通过 rewrite_main_argv 进入 guided flow，但 `_command_guided_tag_v2` 在读取 board 之前调用 `ensure_model_setup`，因此用户先面对模型配置，之后才知道实际处理范围。`_setup_prompt` 将 Ollama 放在第一项，已有 active change 也把它称为 local-first；这与模型来源中立的产品定位不一致。

Eagle client 的 `list_items` 当前只请求一次页面，使用 10000 作为 limit 但没有按 total/offset/limit 继续分页；这可能把大型文件夹静默截断。`update_item` 当前强制发送 tags 和 annotation。`analyze_tag_item` 返回新 tags 和完整新 annotation，写回路径直接使用它们，因此会覆盖人工 tags 和 annotation。`replace_analysis_annotation` 与 `remove_analysis_annotation` 已存在，但主写回和 reset 没有正确使用。当前 `reset` 发送空 tags 和空 annotation，会清空所有用户 metadata。

模型 adapter、JSON schema、prompt、taxonomy 和公共分析结果契约已经工作。本变更围绕 CLI 编排、metadata 边界和文档受众做改造，避免重写 provider 协议。

## Goals / Non-Goals

**Goals:**

- 让 `moodtag <folder>` 成为 board-first、策略驱动的交互任务。
- 默认按 Enter 选择“仅处理未生成描述的图片”。
- Remote API 与 Ollama 在首次设置中平等呈现，已有配置直接复用。
- 保留显式高级 CLI 作为 Agent、脚本和非交互终端接口。
- 在写回前保护人工 tags 和 annotation，并让 reset 只处理 Moodtag 自己的区域。
- 明确定义 missing / valid / malformed 三态处理状态。
- 在每个 item 写回前刷新 Eagle metadata 并重新检查状态。
- 完整分页扫描 folder，确保 board-first 统计和 max-board-items 基于完整数据。
- 将中断范围限制在安全提交，不建设持久化恢复系统。
- 让 README 面向普通用户，把技术细节迁移到专题文档。

**Non-Goals:**

- 不重写 Ollama 原生请求、Remote API 协议、response parser、prompt、taxonomy 或模型 schema。
- 不自动安装 Ollama、不自动下载视觉模型、不把本地失败 fallback 到云端。
- 不删除 `--write`、`--force`、`--limit`、`--max-board-items`、JSON 或高级 dry-run 能力。
- 不在本次实现 AI 标签来源持久化；第一版只做去重合并并保留人工标签。
- 不在普通 README 中承诺固定并发、固定耗时或固定成本。

## Decisions

### 1. Board-first execution order

主命令顺序固定为：

```text
解析 folder → 连接 Eagle → 读取 scope → 显示摘要
                                      ├─ Enter: skip existing
                                      ├─ overwrite existing
                                      └─ exit
                                           │
                                           └─ 需要处理时解析模型配置 → 分析 → 写回
```

读取 scope 不需要模型。用户选择 exit 时不得初始化 provider、请求 API key、连接 Ollama 或修改 Eagle。已有有效模型配置时直接使用，不显示来源菜单。

替代方案：先 setup 模型再扫描 board。放弃原因：用户在看到任务规模前就被配置打断，而且退出时可能触发无关的网络或凭证流程。

### 2. Neutral model-source setup

无有效配置且用户选择处理时，显示两个同等选项：

- Remote API：无需本地模型，配置 endpoint、model 和服务商要求的 API key；可能产生调用费用，图片会上传到服务商。
- Local Ollama：本地运行，不产生远程模型 API 调用费用；需要安装 Ollama 和视觉模型，消耗本机 CPU/GPU/RAM。

Remote API 可以作为第一项以减少新手安装成本，但 UI 使用相同视觉层级，不使用推荐、首选、fallback 等语言。Ollama 服务可达不等于视觉模型可用；必须检查已安装模型及其 vision capability。两种来源都进入同一分析、标签、annotation 和批量处理管线。

替代方案：自动优先 Ollama。放弃原因：产品替用户决定成本、隐私和硬件取舍，也会让没有本地模型的用户多一次失败路径。

### 3. Explicit policy with Enter default

新增内部 WritePolicy：skip-existing、overwrite-existing、exit。菜单第一项为 skip-existing 并支持空输入直接选择；普通主流程不出现 dry-run、--write 或 --force 文案。高级 `tag` 命令保留这些参数。

### 4. Three-state analysis status and reliable annotation boundaries

`skip-existing` 只依据 `has_analysis_annotation` 的可靠验证结果。普通人工 tags、普通 annotation 和空 metadata 都是 missing；完整且可定位的 Moodtag 区块是 valid；字段缺失、重复、边界不明或疑似人工结构化文本的区块是 malformed。malformed 不得静默覆盖，摘要中单独计数并要求用户显式处理。

新写入的 annotation 使用明确的 Moodtag 起止边界。旧格式继续读取，但只有能够确定完整范围时才允许 `replace` 或 `remove`；否则保留原文并报告异常。检测、replace 和 reset 必须共享同一套边界逻辑。

### 5. Safe metadata composition

引入单一写回组合函数：

```text
merged_tags = stable_unique(existing_tags + generated_ai_tags)
merged_annotation = replace_analysis_annotation(existing_annotation, generated_block)
```

Eagle update adapter 接受可选 tags/annotation 字段，只发送需要更新的字段。分析完成后，写回阶段先调用 `item_info(item.id)` 获取最新 tags/annotation，再重新检查状态：skip-existing 若发现有效 Moodtag 结果则跳过；overwrite-existing 才继续替换当前 Moodtag 区域。随后使用最新 metadata 组合写回。普通写回始终用组合后的值。reset 只调用 `remove_analysis_annotation` 并更新 annotation；不发送 tags=[]。在没有 AI 标签归属记录前，reset 不删除标签。

`overwrite-existing` 的用户文案使用“重新生成 AI 描述与标签”。annotation 会替换旧 Moodtag 区块；tags 只保留并去重合并，因此旧 AI tags 可能继续存在。这是当前没有标签来源追踪时的明确限制，不宣称完整标签替换。

替代方案：为所有生成标签增加前缀。暂不采用，因为会改变现有用户标签观感和 taxonomy 契约；归属追踪作为后续独立变更。

### 6. Complete board pagination

`EagleClient.list_items` 必须依据响应中的 total、offset、limit、data 继续请求直到完整收集，兼容 V2 和 V1 fallback 的实际分页字段。folder 去重和 max-board-items 检查只能在完整集合上执行。测试覆盖 1000、1001 和超过门禁的数量，任何无法确认完整性的响应都报错，不得当作完整扫描。

### 7. Provider parity and concurrency wording

不在 CLI 根据来源隐藏功能。移除或重新设计 Ollama concurrency > 1 的硬编码产品错误；如果底层服务确实需要串行，provider 返回明确运行限制，文档只描述实际限制。Remote API 并发也继续受服务商限制。性能说明使用条件化语言，不比较固定快慢。

### 8. Documentation information architecture

README 只包含：安装、打开 Eagle、选择 folder、策略菜单、模型来源取舍、已有 metadata 处理和基本结果。新增或整理：

- docs/getting-started.md
- docs/model-setup.md
- docs/cli-reference.md
- docs/architecture.md
- docs/benchmarks.md
- docs/moodboard.md

采样参数、endpoint、retry、Ollama cloud 控制、模型实验、context/num_ctx、benchmark 和 moodboard layout 从 README 移出。安装文档把 Gatekeeper 的“系统设置 → 隐私与安全性 → 仍要打开”作为用户路径；普通用户文档暂时只展示 GitHub 安装命令，PyPI 和 editable 安装留在维护者文档。

## Risks / Trade-offs

- [skip-existing 误判人工 annotation 为已处理] → 只使用三态 Moodtag 区块检测。
- [分析期间 Eagle 元数据发生变化] → 写回前 item_info 刷新并重检。
- [分页响应被服务端截断] → 读取 total/offset/limit 并验证完整性。
- [旧 annotation 格式边界不可靠] → malformed 单独报告并保留原文。
- [已有用户依赖当前写回覆盖行为] → 这是必要的安全修正；高级命令保留分析能力，但写回也必须遵守 metadata 保留契约。
- [无法区分旧 AI 标签和人工标签] → 第一版只合并不删除；reset 不清空 tags，后续增加归属记录。
- [来源菜单 Remote API 放第一项仍可能被理解为推荐] → 使用对称版式和明确的成本、数据流、安装描述，禁止“首选/备选”措辞。
- [Ollama 服务存在但没有视觉模型] → 单独报告 service reachable 与 vision model ready 状态，不自动 pull 或 fallback。
- [非 TTY 主命令无法选择策略] → 返回稳定错误并指向高级 `tag` 参数；JSON stdout 保持纯结果。
- [分析中断导致已完成结果未写回] → 按分析完成顺序安全写回；中断时保留已经安全提交的结果，下一次扫描重新判断状态，不建设持久化恢复队列。
- [文档迁移遗漏内部参数] → 增加 README smoke check，禁止用户入口出现采样、endpoint 和 benchmark 细节。

## Migration Plan

1. 先实现 metadata-safe writeback 和 reset 防护，添加回归测试。
2. 实现 board-first guided flow 与 source-neutral setup，保留高级命令兼容行为。
3. 更新输出契约、帮助文本和 README，再迁移专题文档。
4. 运行完整测试与文档检查后发布；若回滚，只回滚 guided 编排和文档，保留 metadata 安全修复。

## Open Questions

- Ollama 多模型在用户选择本地来源后显示一次选择菜单；只有一个兼容视觉模型时自动选择，并持久化用户确认的模型。
- 非 TTY 主命令不新增策略参数，统一使用高级 `tag` 命令。
- metadata-safe writeback 与 guided UX 保持同一 OpenSpec change，但实现时先独立提交并先通过安全测试。
