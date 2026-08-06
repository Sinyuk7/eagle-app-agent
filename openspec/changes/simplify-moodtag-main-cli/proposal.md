## Why

`moodtag` 目前更像维护者导向 CLI，而不是设计师、摄影师这类非技术 Mac 用户可直接上手的产品。主流程需要先安装开发者工具、理解 `--board`、区分 dry run 与 `--write`，再自己判断递归范围、覆盖风险和配置状态，这和“一步安装、一条命令、确认后执行”的目标不一致。

现在需要把产品主路径收束成面向终端用户的默认体验，同时保留现有高级命令给维护者和重度用户使用。这样后续包装成 `pkg` 或 `dmg` 时，安装、首次运行、帮助文档和交互逻辑才能形成一致产品心智。

## What Changes

- 将核心打标入口收束为单一主命令：`moodtag <board-url-or-id>`。
- 让主命令同时接受 Eagle folder URL 和 folder ID，不再要求用户先手动提取 `id=`。
- 让主命令默认进入 guided flow：先解析目标文件夹、显示范围和风险摘要，再等待用户确认后开始写回。
- 让主命令在首次缺少 API key 时自动进入 setup，并把 key 保存到 `~/.config/moodtag/.env`。
- 将现有多参数、维护者导向的命令面降级为 secondary surface，保留 `--help` 与 `config` 作为必要支持能力。
- 为 macOS 提供面向终端用户的主安装路径，优先 `pkg` 或 `dmg`，而不是要求预先具备 `uv`、Python 或其他开发者工具。
- 更新 README、帮助文本和安装文档，使“主路径”和“高级路径”清晰分层。

## Capabilities

### New Capabilities
- `guided-tagging-cli`: 提供单命令主流程、board URL 解析、执行前摘要和交互确认。
- `mac-installer-distribution`: 提供面向 macOS 终端用户的主安装分发方式和对应文档入口。

### Modified Capabilities

- None.

## Impact

- Affected code: `moodtag/cli.py`, board 参数解析与命令分发逻辑，用户可见 stdout/stderr 文案。
- Affected docs: `README.md`, 安装说明、首次运行说明、帮助文本。
- Affected distribution/release: macOS 安装包构建、发布说明、验证流程。
- Affected tests: CLI 参数解析、交互确认、URL/ID 输入兼容性、主路径安装与文档 smoke checks。
