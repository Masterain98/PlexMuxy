# Plex 视频批量封装工具（PlexMuxy）

PlexMuxy 用于将视频、外挂音频、ASS/SSA 字幕和字体安全地批量封装为 Matroska 文件。CLI 与桌面 GUI 共用同一套计划和执行服务。

## 数据安全保证

- `plan` 只生成计划，不修改媒体文件；可用 `--json` 保存可审查的计划快照。
- 执行使用同一份快照。输入文件、输出状态或配置发生变化时返回 `PLAN_STALE`，要求重新生成计划。
- 混流先写临时文件；只有 `mkvmerge -J` 验证容器、轨道、语言、名称、默认/强制标记和附件后，才原子替换正式输出。
- 只有 `success=true` 且 `verified=true` 的任务才可清理。共享资源必须等所有依赖任务成功后才会移动或删除。
- 删除必须显式提供 `--yes`，覆盖必须显式启用。失败的临时输出默认改名为 `*.mkv.failed`。

## 安装

需要 Python 3.10–3.13 和 [MKVToolNix](https://mkvtoolnix.download/)。请把 `mkvmerge` 加入 `PATH`，或配置 `mkvmerge.path`。

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

可用覆盖参数包括 `--output-dir`、`--output-suffix`、`--name-strategy`、`--name-template`、`--extra-dir`、`--overwrite` 和 `--cleanup`。

## 配置与兼容性

默认配置位置：Windows 为 `%APPDATA%\PlexMuxy\config.json`，macOS 为 `~/Library/Application Support/PlexMuxy/config.json`，Linux 为 `$XDG_CONFIG_HOME/plexmuxy/config.json`。

程序会拒绝未来版本、损坏配置、未知根字段、重复语言配置、非法模板和无效并发数量。旧配置在 0.2 中仍可读取，建议立即执行 `migrate-config`；0.3 只保留导入兼容，1.0 将移除旧入口。

默认匹配策略保守：`movie_fallback=false`、最低置信度 0.7、歧义项跳过。并发配置为 `max_parallel_mux_jobs`，范围 1–4，默认 1；旧 `thread_count` 仅用于迁移。

## 文件匹配

优先级为：完全同名（1.0）→ 标准化标题（0.85）→ 标准化集数身份（0.70）→ 可选的单视频电影回退。支持 `[1]`、`[100]`、`S01E01`、`S01EP01`、`E01`、`EP01`、`.01.`、`SP01`、`Special`、`OVA`。

一个资源若对多个视频具有相同最高分，会以 `ambiguous_match` 跳过；低于阈值则为 `unmatched`。程序不会按文件排序猜测归属。

## 字体、压缩包和源轨道

`font.mode=all` 默认附加全部字体；`referenced` 会读取 ASS/SSA 样式字体与 `\fn` 覆盖标签；找不到字体时按 `missing_font_action` 处理。`subset` 当前安全回退为“引用到的完整字体”，不会生成已知缺字的子集。

ZIP/7z 在写入前检查压缩包大小、文件数、展开总大小、单文件大小和目录深度，并阻止路径穿越；RAR 无法可靠预检时必须显式允许。同名同内容字体去重，同名不同内容字体自动改名并报告冲突。

计划阶段会读取源容器轨道并展示。0.2 的产品决策是默认保留全部源轨道；未知语言、无标题轨道不得自动删除。

## 开发与验证

```bash
pip install -e ".[dev,build]"
pytest -m "not integration"
pytest -m integration
ruff check plexmuxy plexmuxy_gui tests
mypy plexmuxy plexmuxy_gui
python -m build
```

更多内容见 [架构说明](docs/architecture.md)、[故障排查](docs/troubleshooting.md)、[安全说明](docs/security.md) 和 [发布流程](docs/release-process.md)。

## 许可证

MIT
