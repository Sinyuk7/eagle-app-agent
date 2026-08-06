## Context

`moodtag` 目前是 command-first CLI：无参数失败，bare board 进入单次 guided flow，输出由散落的 `print()` 组成。它已拥有 Eagle scope 解析、单 provider adapter、first-image probe 和 JSONL telemetry，但没有面向普通用户的持续状态、终端 renderer、输出协议或可恢复的取消模型。

本 change 把产品表面改为 workflow-first：用户启动 `moodtag` 后先看到“现在能做什么、当前是否就绪”，然后只聚焦下一步。所有已经决定的范围都保留：profile persistence、model catalog、废弃配置清理、流式 UI、quiet levels、stdout/stderr、两种终端 renderer 和 UI 模块边界。

## Goals / Non-Goals

**Goals:**

- 让无参数 TTY 启动成为状态优先的工作流首页，而不是 argparse 错误或 command 菜单。
- 用自然语言呈现 board 确认、处理过程和最终结果；每个时刻只保留一个视觉焦点。
- 使用 `yaspin` 和 `alive-progress` 提供平滑、可访问、TTY-safe 的动态反馈。
- 使分析和写入具有诚实的“准备、分析、写入、完成”阶段，并显示最近完成的 2 到 3 个图片。
- 定义 stdout/stderr、`--json`、`-q`/`-v`/`-vv`、ANSI/`NO_COLOR` 和敏感输出边界。
- 以两个资源文件维护固定模型 catalog；模型 ID 唯一推导 protocol，普通用户只配置 URL、模型、API key。
- 持久化 profile，并把配置工作流整合进状态首页和 `moodtag config`。

**Non-Goals:**

- 不引入全屏 TUI、curses 或方向键依赖。
- 不修改 Chat/Responses wire payload、endpoint URL 规范化、重试语义、secret 文件权限或图像分析合同。
- 不承诺 Ctrl-C 回滚已经写入 Eagle 的项目。

## Decisions

### 1. Workflow-first home screen

无参数且 stdin/stdout 均为 TTY 时进入状态首页。首页先显示欢迎语、`AI 已配置/需要配置`、当前 profile，再显示 `开始打标签`、`更换 Profile`、`配置 AI`、退出。它不是 command reference；数字只是可靠的键盘输入。默认不显示 provider、endpoint、模型 ID 或日志路径。

bare board URL、ID、名称或路径候选仍直接进入 tagging workflow；显式高级命令继续使用 argparse。非 TTY 无参数运行不读取 stdin，输出可执行提示并失败。

### 2. Natural-language confirmation and one focus

board 成功解析后，确认页使用“将分析”语言：已解析的 board 名称、总图片数、需要分析数、已完成数、profile 和 `AI 已配置`。不显示 Target、Scope、Provider、host 或内部 ID。用户确认后，确认页成为历史内容；renderer 清除或覆盖活动状态区域，避免 Summary 与进度争夺注意力。终端不支持控制序列时降级为简短线性文本。

### 3. Honest execution phases

执行模型重组为：准备（连接 Eagle、读取 scope、检查配置、first-image probe）→ 并发分析所有候选项 → 写入成功分析结果 → 完成。默认 scope 至多 100 项，分析结果仅包含 tags/annotation，允许在内存中暂存以换取真实写入阶段、明确取消语义和连贯 UI。

每个阶段只显示用户可理解的名称。`-v` 可显示 item 结果；`-vv` 才展示内部阶段、endpoint、model、HTTP 诊断与 timing。首个 probe 失败时不进入批量分析或写入。

### 4. Renderer ownership and UI boundary

新增 `moodtag/ui/`：

```text
ui/
  ansi.py       TTY/颜色能力、清行、光标移动
  spinner.py    yaspin adapter，仅用于未知总量的短等待
  progress.py   alive-progress adapter，仅用于已知总量的阶段
  printer.py    语义化人类输出，统一 stderr
  menu.py       数字选择、返回、取消、重试
```

业务层禁止直接 `print()` 人类 UI。一个 session coordinator 负责阶段切换，确保 yaspin 和 alive-progress 不并发写同一流。`yaspin` 完成后固定输出 `✓` 结果；alive bar 接管后展示进度、ETA、FPS 和最近完成项目。进度的最近项目优先使用 renderer text/受控行，避免并发 `print()` 破坏动画。

### 5. Symbols, color, and accessibility

产品全局只使用 `○` 等待、`…` 进行中、`✓` 成功、`!` 注意/跳过、`×` 失败、`→` 下一步。颜色仅增强状态：cyan 进行中、green 成功、yellow 注意、red 失败、dim 次要信息。每个颜色状态必须有符号和文字。

非 TTY、`TERM=dumb`、`NO_COLOR=1` 或 `--plain` 禁用 ANSI 与动画；renderer 输出稳定的换行文本。宽度不足时省略 ETA/FPS 和最近项目，优先保留阶段、完成数与失败数。

### 6. Output contract and quiet levels

stdout 仅承载机器数据：目前 `--json` 的最终单一 JSON 文档。stderr 承载人类 UI、spinner、progress、verbose item 日志、诊断和错误。因此 `moodtag <board> --json | jq` 不会混入进度控制符。

输出等级：

```text
-q       仅最终摘要和错误
default  状态首页、确认、活动反馈、完成摘要
-v       default 加每项成功/跳过/失败记录
-vv      -v 加 endpoint、模型、HTTP 类别、重试、timing；不含 key、Authorization、prompt、图片或原始响应
```

`--json` 改变 stdout 格式，不取消 stderr 上的错误；在非 TTY 下默认无动画。机器 JSON 的 schema、退出码和错误字段需稳定且测试覆盖。

### 7. Two resource-backed model catalogs and minimal configuration

新增 `moodtag_core/resources/models/chat.json` 与 `responses.json`。文件路径定义 protocol；条目包含 model ID、显示名称和可选 `recommended`。初始内容是 Chat 的 `qwen3.5-122b-a10b`，Responses 的推荐 `gpt-5.6-luna` 与 `gpt-5.6-terra`。loader 验证非空、跨文件唯一、recommended 至多一个，并提供 `model -> protocol`。

配置 AI workflow：选择 Chat/Responses → 从该 catalog 选择模型 → 输入 URL → 隐藏输入/保留 API key → 显示红acted summary → 确认原子保存。模型服务只持久化 JSON 的 `base_url`、`model` 和 owner-only `.env` 的 `MOODTAG_API_KEY`。`profile` 和 `eagle_api` 独立保存。普通 UI 只显示“AI 已配置”，不显示 internal variable 名。

删除 `protocol` JSON 字段、`MOODTAG_PROTOCOL`、`MOODTAG_BASE_URL`、`MOODTAG_MODEL`、`config set --protocol`、自由文本 Protocol/Model prompt。0-user beta 不读取、不兼容、不转换旧 provider JSON 或环境变量；配置必须符合当前契约。`MOODTAG_API_KEY` 仅是 owner-only secret 文件中的内部键名，并可作为明确的自动化临时覆盖；状态页面只显示 override 来源，绝不泄露值。

### 8. Configuration command workflow

```text
moodtag config                   查看用户状态
moodtag config profile            交互选择 profile
moodtag config profile editorial  直接保存 profile
moodtag config model              配置 AI workflow
moodtag config reset              交互选择重置 Profile、AI 配置或全部
```

`config reset` 必须在删除 API key 前显示确切影响并要求确认。旧 `config set/get/unset` 风格及其实现、文档、测试、示例直接删除；beta 不提供兼容期。

## Risks / Trade-offs

- [两种 renderer 争抢终端] → session coordinator 保证 spinner/progress 生命周期互斥，并以伪 TTY 测试覆盖切换。
- [批量分析后写入增加暂存] → scope 上限和小型结果对象控制内存；减少部分写入和阶段歧义。
- [部分写入仍不可回滚] → 确认与取消摘要明确已写、未写数量。
- [外部依赖影响打包] → 锁定运行时依赖、在 macOS installer 和 plain fallback smoke test 中验证。
- [stdout/stderr 改变脚本行为] → `--json` 提供稳定数据通道；README 直接说明 stdout 只承载机器数据。
- [废弃配置/环境变量] → beta 直接删除相关读取与入口；仅接受当前配置契约，绝不猜测 protocol。

## Implementation Plan

### Phase 1: Terminal foundation and workflow

1. 恢复 single-provider 改造中删减的 CLI 回归覆盖，修复未转换异常。
2. 加入 UI boundary、stderr printer、TTY detection、home screen、确认页面和 profile persistence。
3. 加入 yaspin/alive-progress，并在现有执行流程上提供安全 fallback。

### Phase 2: Execution and output contract

1. 重组为准备/分析/写入阶段，接入流式最近结果和 cooperative cancellation。
2. 实现 stdout/stderr、`--json`、`-q`/`-v`/`-vv`、`NO_COLOR` 和 `--plain`。

### Phase 3: Catalog and configuration cleanup

1. 加入两个 model resources、loader、catalog setup 和 protocol derivation。
2. 直接删除废弃 provider 配置、环境变量和旧 config commands 的读取、入口、文档、测试与示例。
3. 更新 README、help、`.env.example`、installer smoke checks 与 live protocol matrix，描述当前 beta 契约。

UI 可按需回退为旧线性输出；废弃 provider 配置不在 beta 支持范围内，也不提供兼容说明。

## Open Questions

- `config reset` 的“Profile / AI / 全部”选择是否应支持命令行非交互选择，还是只提供安全交互选择？
- `--json` 是否在成功时包含每项完整 tags/annotation，还是只包含摘要与失败项目？
- 是否在后续 release 加入 `MOODTAG_LANG`，还是先固定中文 UI？
