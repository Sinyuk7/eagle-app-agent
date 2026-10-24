## Why

Moodtag 当前把模型配置、Eagle 扫描、写回风险和维护者参数混在同一套产品入口里。README 又把 Ollama 描述为首选、把 Remote API 描述为备选，并暴露采样参数、endpoint、并发和 moodboard 内部工具，普通用户必须先理解实现细节才能完成一次图片整理。

同时，现有写回逻辑会用 AI 结果直接替换 Eagle 的 tags 和 annotation，reset 甚至会清空全部标签和备注。这些行为可能破坏用户手工整理的数据，必须和交互重构一起修正。

## What Changes

- **BREAKING** 将主命令改为 board-first 交互任务：先扫描 Eagle 文件夹、展示图片和元数据统计，再选择跳过已有描述、重新生成全部或退出。
- **BREAKING** 普通主流程不再要求用户理解 dry run、--write、--force、--limit、--max-board-items、endpoint 或 profile；这些显式参数保留给 Agent、脚本和维护者使用。
- **BREAKING** 首次模型配置只在用户选择处理且没有有效配置时出现；Remote API 与本地 Ollama 作为平等的一等选项，已有有效配置直接沿用。
- Remote API 和 Ollama 都必须支持完整的图片分析、标签生成、备注写回和批量处理能力；不添加本地优先、远程 fallback 或来源特定的产品限制。
- 明确说明本地成本、远程费用、图片数据流、安装要求、硬件影响、服务商并发和网络因素；不作绝对速度承诺。
- 修正 Eagle 写回：合并去重 AI tags 与已有 tags，只替换 Moodtag 自己的 annotation 区域，保留人工 metadata；重新生成时明确旧 AI tags 可能继续保留。
- 将 Moodtag 处理状态定义为 missing / valid / malformed：skip-existing 只跳过有效 Moodtag 描述，人工 tags 或普通 annotation 不代表已处理；残缺区块单独报告异常。
- 写回前重新获取当前 Eagle item metadata，并重新检查处理状态，避免分析期间的人工修改被旧快照覆盖。
- 修正 Eagle 文件夹列表分页，完整读取所有页面后再去重、统计和执行 max-board-items 门禁，禁止静默截断。
- 为 Moodtag annotation 增加可靠边界；旧格式仅在能确认完整范围时替换或删除，边界不确定时保留原文并报告异常。
- 修正 reset：只移除 Moodtag annotation 内容，不清空无法安全归属的人工 tags；在实现标签归属前不把 destructive reset 暴露给普通用户。
- 重新评估 Ollama 的硬编码串行限制，让产品文档不再错误宣称本地不支持并发；区分 CLI concurrency 与 Ollama server parallelism。
- 不引入持久化任务队列、checkpoint 或后台恢复系统；只保证已成功返回并安全写回的结果在中断后保留，下一次扫描可继续跳过。
- 将 README 收敛为安装、文件夹选择、模型来源取舍、生成描述和已有 metadata 策略；把高级 CLI、模型调优、benchmark、架构和 moodboard 文档拆分到 docs/。
- 修正 macOS Gatekeeper 说明；普通安装文档暂时只提供 GitHub 安装命令。

## Capabilities

### New Capabilities

- `board-first-guided-workflow`: 扫描 Eagle、展示处理范围，并通过默认策略菜单驱动主任务。
- `model-source-neutral-setup`: 按需配置 Remote API 或本地 Ollama，保持来源能力平等且不自动 fallback。
- `metadata-safe-writeback`: 合并标签、局部替换 annotation，并提供安全 reset 行为。
- `advanced-cli-contract`: 保留 Agent/脚本需要的显式参数、JSON 输出和非交互接口，同时与普通用户入口分层。
- `documentation-information-architecture`: 重写 README 并拆分用户文档、CLI reference、model setup、benchmarks、architecture 和 moodboard 内容。

### Modified Capabilities

<!-- No main specs exist yet; these capabilities are introduced by this change. -->

## Impact

- 主要代码：`moodtag/cli.py`、`moodtag/config.py`、`moodtag/ui/menu.py`、`moodtag_core/annotation.py`、Eagle client update adapter、Ollama concurrency guard。
- 主要测试：guided workflow、model catalog/config、metadata merge/reset、provider parity、TTY/non-TTY/JSON output、documentation smoke checks。
- 主要文档：`README.md`、`CONTRIBUTING.md` 和新增 `docs/` 专题文档。
- 外部系统：Eagle 本地 API、可选 Ollama 服务、可选远程 OpenAI-compatible 服务。
- 本次不重写已正常工作的模型请求协议、响应解析、prompt、taxonomy 或 provider adapter；只调整产品入口、安全写回和文档边界。
