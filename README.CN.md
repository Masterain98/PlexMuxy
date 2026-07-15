<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./logo/svg/plexmuxy-lockup-dark.svg" />
    <source media="(prefers-color-scheme: light)" srcset="./logo/svg/plexmuxy-lockup-light.svg" />
    <img src="./logo/svg/plexmuxy-lockup-light.svg" width="640" alt="PlexMuxy" />
  </picture>
</p>

# Plex 媒体封装与元信息整理工具（PlexMuxy）

PlexMuxy 按照 Plex Media Server 的扫描、播放和元信息识别习惯规划并生成 Matroska 文件。它会匹配外挂音轨与 ASS/SSA 字幕、附加字幕所需字体，并写入轨道语言、名称、标记等元信息，让 Plex 能正确发现、加载和呈现这些额外内容。例如，字幕轨道不仅会显示语言，还可以保留从文件名识别出的字幕组信息，而不是成为没有名称的普通轨道。CLI 与桌面 GUI 共用同一套计划和执行服务。

## 数据安全保证

- `plan` 只生成计划，不修改媒体文件；可用 `--json` 保存可审查的计划快照。
- 执行使用同一份快照。输入文件、输出状态或配置发生变化时返回 `PLAN_STALE`，要求重新生成计划。
- 混流先写临时文件；只有 `mkvmerge -J` 验证容器、轨道、语言、名称、默认/强制标记和附件后，才原子替换正式输出。
- 只有 `success=true` 且 `verified=true` 的任务才可清理。共享资源必须等所有依赖任务成功后才会移动或删除。
- 删除必须显式提供 `--yes`，覆盖必须显式启用。失败的临时输出默认改名为 `*.mkv.failed`。

## 安装

需要 Python 3.10–3.14 和 [MKVToolNix](https://mkvtoolnix.download/)。请把 `mkvmerge` 加入 `PATH`，或配置 `mkvmerge.path`。

```bash
pip install plexmuxy
plexmuxy --help
```

桌面 GUI：

```bash
pip install "plexmuxy[gui]"
plexmuxy gui
# 或 plexmuxy-gui
```

Windows GUI 采用 Microsoft Edge WebView2 Evergreen Runtime。Windows 11 通常已自带；Windows 10 可能需要安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。正式发布的 Windows CLI/GUI 压缩包不依赖本机 Python，请使用 `SHA256SUMS.txt` 校验下载文件。

## 命令示例

```bash
plexmuxy init-config
plexmuxy show-config

# 原地迁移会先创建 config.json.bak-时间戳
plexmuxy migrate-config
plexmuxy migrate-config --source old.json --target new.json

# 预览、保存并执行完全相同的计划
plexmuxy plan D:\Media --json plan.json
plexmuxy execute-plan plan.json

# 一次性执行
plexmuxy mux D:\Media --cleanup none

# 删除策略必须确认
plexmuxy mux D:\Media --cleanup delete --yes

# 导出不含媒体文件和完整用户路径的诊断包
plexmuxy diagnostics --output diagnostics.zip
```

可用覆盖参数包括 `--output-dir`、`--output-suffix`、`--name-strategy`、`--name-template`、`--extra-dir`、`--font-mode`、`--overwrite` 和 `--cleanup`。例如 `--font-mode subset` 会为本次计划启用字体子集化。

## 配置与兼容性

默认配置位置：Windows 为 `%APPDATA%\PlexMuxy\config.json`，macOS 为 `~/Library/Application Support/PlexMuxy/config.json`，Linux 为 `$XDG_CONFIG_HOME/plexmuxy/config.json`。

程序会拒绝未来版本、损坏配置、未知根字段、重复语言配置、非法模板和无效并发数量。旧配置在 0.2 中仍可读取，建议立即执行 `migrate-config`；0.3 只保留导入兼容，1.0 将移除旧入口。

默认匹配策略保守：`movie_fallback=false`、最低置信度 0.7、歧义项跳过。并发配置为 `max_parallel_mux_jobs`，范围 1–4，默认 1；旧 `thread_count` 仅用于迁移。

桌面端的“环境配置”是独立于任务工作流的持久化页面。每个依赖项都会显示已验证的可执行文件、发现来源和版本。“自动检测”会立即重新探测并将结果保留为未保存草稿，绝不会静默替换已保存的显式路径。Windows 还会扫描 HKLM/HKCU 的 32/64 位卸载信息来发现 MKVToolNix。UnRAR 操作只允许通过白名单 HTTPS 下载 RARLAB 的已签名 x64 安装包，由官方安装程序完成安装，并在用户确认保存前把检测结果作为候选项显示。Windows 构建在创建原生窗口前启用 Per-Monitor V2 DPI 感知，因此文件选择器和 WebView 在高分辨率、多显示器环境中使用系统缩放。

Windows 可在该页面启用任务结束通知。当前实现使用 Windows Shell 的原生通知区域后端，覆盖任务完成、失败和取消；通知不可用不会影响封装结果。需要应用激活、操作按钮和通知中心身份的 Windows App SDK 通知属于后续安装器/应用身份工作。

## 文件匹配

优先级为：完全同名（1.0）→ 标准化标题（0.85）→ 标准化集数身份（0.70）→ 可选的单视频电影回退。支持 `[1]`、`[100]`、`S01E01`、`S01EP01`、`E01`、`EP01`、`.01.`、`SP01`、`Special`、`OVA`。

一个资源若对多个视频具有相同最高分，会以 `ambiguous_match` 跳过；低于阈值则为 `unmatched`。程序不会按文件排序猜测归属。

## 支持的文件类型

PlexMuxy 读取以下来源格式，并始终输出为 Matroska（`.mkv`）容器：

| 角色 | 扩展名（默认） |
| --- | --- |
| 视频容器 | `.mkv`、`.mp4`、`.avi`、`.flv` |
| 外挂字幕 | `.ass`、`.ssa` |
| 外挂音频 | `.mka` |
| 字体附件 | `.ttf`、`.otf`、`.ttc`、`.otc` |
| 字体压缩包 | `.zip`、`.7z`、`.rar` |

视频容器列表可在 `config.json` 的 `media.video_extensions`（以及其它 `media.*_extensions` 列表）中配置，因此也可以启用 `mkvmerge` 能够解封装的其它容器。输出始终为 Matroska，这正是 Plex 期望的格式。

针对 issue #14 中的场景：PlexMuxy 已经可以把 `.avi` 视频与 `.ssa` 字幕封装为单个 `.mkv`。可参考[命令示例](#命令示例)与[配置与兼容性](#配置与兼容性)中的 `--output-dir`、`--name-strategy`、`--cleanup` 等任务参数，控制输出位置和文件命名方式。

## 字体、压缩包和源轨道

`font.mode=all` 默认附加全部字体；`referenced` 使用 ASS/SSA 结构解析与字体内部名称选择完整字体；`subset` 会真正生成只含所需字符的字体附件。子集模式按动态 `Format`、Style 和 override 状态解析 `\fn`、`\r`、`\b`、`\i`、`\p` 与 `\t(...)`，枚举 TTF/OTF/TTC/OTC 的全部 face，并按内部 family、weight、italic 和 cmap 做确定性匹配。临时字幕只把已验证 family 改为 `PMX_<hash>` alias，源字幕和源字体不会被修改。

所有视频的子集字体和临时字幕必须先在执行专用工作区完成并重新验证，之后才会启动任何 `mkvmerge` 进程。同一执行中的相同子集会复用缓存；工作区在成功、失败或取消后统一删除。FontTools 无法安全处理某个已匹配 family 时，默认只为该 family 附加完整原字体并保留原字体名；字体缺失、匹配歧义、缺字、无法安全解析的 ASS 或无法区分的无 BOM GB18030/CP932 编码不会静默继续。可通过 `missing_font_action` 和 `subset_failure_action` 选择跳过视频、终止任务或允许的完整字体回退。

ZIP/7z 在写入前检查压缩包大小、文件数、展开总大小、单文件大小和目录深度，并阻止路径穿越；RAR 无法可靠预检时必须显式允许。同名同内容字体去重，同名不同内容字体自动改名并报告冲突。

输出验证会同时核对字体附件名称和 MIME type。计划阶段也会读取源容器轨道并展示；默认保留全部源轨道，未知语言和无标题轨道不得自动删除。

## 开发与验证

使用 `uv` 创建包含开发和 GUI 依赖的本地环境：

```bash
uv sync --extra dev --extra gui
```

### 从源码调试 CLI

通过包模块启动，工作树中的代码修改会直接生效：

```bash
uv run python -m plexmuxy show-config
uv run python -m plexmuxy plan D:\Media --json plan.json
```

使用 IDE 调试时，Windows 选择 `.venv/Scripts/python.exe`，macOS/Linux 选择 `.venv/bin/python`；启动模块填写 `plexmuxy`，并在调试配置中填写所需 CLI 参数。常用断点入口为 `plexmuxy/cli.py` 和 `plexmuxy/service.py`。

### 从源码调试 GUI

设置 `PLEXMUXY_GUI_DEBUG=1` 会启用详细日志和 pywebview/WebView2 开发者模式：

```powershell
# PowerShell
$env:PLEXMUXY_GUI_DEBUG = "1"
uv run --extra gui python -m plexmuxy_gui.app
Remove-Item Env:PLEXMUXY_GUI_DEBUG
```

```bash
# macOS/Linux
PLEXMUXY_GUI_DEBUG=1 uv run --extra gui python -m plexmuxy_gui.app
```

使用 IDE 调试时，以相同环境变量启动 `plexmuxy_gui.app` 模块。Python 桥接代码位于 `plexmuxy_gui/api.py`，共享执行路径位于 `plexmuxy/service.py`，前端代码位于 `plexmuxy_gui/static/app.js`。GUI 日志位置为：Windows 的 `%APPDATA%\PlexMuxy\logs`、macOS 的 `~/Library/Application Support/PlexMuxy/logs`，或 Linux 的 `$XDG_CONFIG_HOME/plexmuxy/logs`。

### 验证与构建

```bash
uv run --extra dev pytest -m "not integration"
uv run --extra dev pytest -m integration       # 需要 ffmpeg 和 mkvmerge
uv run --extra dev ruff check plexmuxy plexmuxy_gui tests
uv run --extra dev mypy plexmuxy plexmuxy_gui
uv run --extra dev python -m build

# 构建独立程序前安装 build 额外依赖。
uv sync --extra dev --extra gui --extra build
uv run --extra build python -m PyInstaller --clean --noconfirm plexmuxy-cli.spec
uv run --extra build python -m PyInstaller --clean --noconfirm plexmuxy-gui.spec
```

更多内容见 [架构说明](docs/architecture.md)、[故障排查](docs/troubleshooting.md)、[安全说明](docs/security.md) 和 [发布流程](docs/release-process.md)。

## 许可证

MIT
