## Why

`moodtag` 已有单 board guided flow，但仍以 argparse 和维护者命令为中心：无参数启动直接报错，交互输出冗长，没有统一的进度、取消或 TTY 反馈策略。已完成的单 provider 改造仍把 protocol、环境变量、自由文本模型输入同时暴露给用户，造成一个模型服务有多套重复概念。

## What Changes

- 无参数且连接到 TTY 时显示 workflow-first 状态首页：欢迎语、AI readiness、当前 profile 和下一步操作；数字仅是输入方式，不是产品焦点。
- 检测到 board URL、ID、名称或路径候选时，直接进入 board guided flow；已知高级命令继续交给 argparse。
- 选择的 profile 写入非敏感用户配置，后续运行沿用，直到用户再次切换；显式单次参数优先于持久化值。
- profile 选择提供当前值、可用 profile 和返回主菜单路径。
- 模型服务只持久化服务 URL、固定模型 ID 和 API key；protocol 由模型 catalog 推导，不作为用户输入、配置字段或环境覆盖。
- 从 package resources 读取两个可维护的模型 catalog：Chat Completions 包含 `qwen3.5-122b-a10b`；Responses 包含推荐的 `gpt-5.6-luna` 和 `gpt-5.6-terra`。
- provider 菜单使用 catalog 选择模型、输入服务 URL、隐藏输入 API key，并在确认后原子保存；不重新引入 vendor 或 fallback 概念。
- 清理废弃的 `protocol` 配置、`MOODTAG_PROTOCOL`、`MOODTAG_BASE_URL`、`MOODTAG_MODEL`、自由文本 protocol/model 输入和相应文档、测试、示例。
- 为 TTY 提供“准备、分析、写入、完成”分阶段状态、流式最近完成项目、完成摘要、语义颜色和稳定符号。
- 使用 `yaspin` 显示短暂的未知时长等待，使用 `alive-progress` 显示图片分析/写入进度、ETA 和活动状态；两个 renderer 不同时控制终端。
- 定义 stdout/stderr 契约：UI、进度、日志和错误写 stderr；结构化 `--json` 结果只写 stdout。
- 定义 `-q`、默认、`-v`、`-vv` 输出等级；详细 endpoint、模型、HTTP、prompt 和 timing 只在允许的等级出现，敏感值永不输出。
- 在分析和写回期间支持可恢复的 Ctrl-C 取消，并准确报告已经完成、跳过、失败和未处理数量。
- 默认输出采用简洁中文用户文案；详细内部信息移入 `--verbose` / `--debug`，错误与机器输出分离。
- 保留现有高级 `status`、`tag`、`brief`、`export-context`、`reset` 命令，不改变其自动化用途。

## Capabilities

### New Capabilities

- `moodtag-cli-navigation`: 提供无参数菜单、board 直达、profile/provider 子流程和 TTY/non-TTY 分流。
- `moodtag-profile-preference`: 持久化用户最近选择的 profile，并定义配置优先级。
- `moodtag-model-catalog`: 从两个资源文件加载固定模型、推导协议、保存精简模型服务配置并直接删除废弃字段支持。
- `moodtag-cli-feedback`: 提供分层输出、颜色/符号策略、进度反馈、取消和最终摘要。
- `moodtag-cli-output-contract`: 定义 stdout/stderr、JSON、TTY fallback、quiet levels 和敏感信息边界。

### Modified Capabilities

<!-- No main specs exist yet; the previous guided-flow change is already archived. -->

## Impact

- 主要代码：`moodtag/cli.py`、`moodtag/config.py`、新的 `moodtag/ui/`、新的 `moodtag_core` model catalog/resource loader、`moodtag_core/provider.py`。
- 运行时依赖：`alive-progress`、`yaspin`。
- 测试：CLI argv 分流、catalog 加载、干净 beta 配置契约、TTY workflow、stdout/stderr、颜色/纯文本输出、流式进度、quiet levels 和 Ctrl-C。
- 文档：README、`moodtag --help`、配置说明。
- 0-user beta：直接采用新用户配置契约，不提供旧配置或旧环境变量的兼容与转换；保留 Chat/Responses adapter、单 endpoint、原子 secret 写入和 first-image probe。
