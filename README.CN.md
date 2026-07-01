# Plex 视频批量封装工具 (PlexMuxy)

PlexMuxy 是一个将字幕组/压制组发布作品进行封装的 Python 脚本，它会将外挂字幕、外挂音频、字幕字体文件进行打包，以允许 Plex 服务器能以最好的方法使用这些资源。

中文 README | [English README](https://github.com/Masterain98/PlexMuxy/blob/main/README.md)

## 功能和说明

- 将 `mkv`/`mp4`/`avi`/`flv` 视频文件、`mka` 音频文件、`ass`/`ssa` 字幕文件和字体文件重新打包混流成一个`mkv` 格式的单文件
  - 音频
    - 外挂的音频文件通常为5.1声道或评论轨
  - 字幕
    - 通过文件名判断字幕的语言，包括简体中文、繁体中文、日语、简日、繁日
      - 简中字幕轨道使用 `chs` 作为名称，轨道语言标记为 `chi`
      - 繁中字幕轨道使用 `cht`作为名称，轨道语言标记为 `chi`
      - 日语字幕轨道使用 `jpn` 作为名称，轨道语言标记为 `jpn`
      - 简日字幕轨道使用 `jp_sc` 作为名称，轨道语言标记为 `chi`
      - 繁日字幕轨道使用 `jp_tc`作为名称，轨道语言标记为 `chi`
    - 通过文件名判断字幕作者并将其名称加入字幕轨道
  - 字体
    - 字体文件以附件形式与每一个视频一起打包
    - 这是为了让 Plex 加载字体以保证完整的字幕特效，但会浪费额外的储存空间；当你可以制作字体子集时，建议使用子集字体以减小字体包的大小
- 根据设置，自动删除原始文件或将原始文件移动至统一的目录以避免 Plex 的媒体扫描

## 使用说明

- 下载并安装 [MKVToolNix](https://mkvtoolnix.download/) 并添加其进入 `PATH` 系统变量，或在配置文件中设置 `mkvmerge.path`。

- 本地开发安装：

  ```bash
  pip install -e ".[dev]"
  ```

- 安装可选桌面 GUI：

  ```bash
  pip install -e ".[gui]"
  plexmuxy-gui
  ```

  `plexmuxy gui` 保留为兼容启动入口。基础 CLI 安装不会安装 `pywebview`，因此纯命令行环境不会被 GUI 依赖污染。

- 创建或查看配置：

  ```bash
  plexmuxy init-config
  plexmuxy show-config
  ```

- 预览 mux 计划，不改变文件系统：

  ```bash
  plexmuxy plan /path/to/media
  ```

  `plan` 是 dry-run：只扫描文件、生成 `MuxPlan`、打印匹配原因和跳过原因，不调用 `mkvmerge`，不创建输出文件，不移动或删除文件。

- 执行 mux：

  ```bash
  plexmuxy mux /path/to/media
  ```

  默认输出仍保持旧行为：生成 `_Plex.mkv`。默认 cleanup 为 `move`，只在 mux 成功且输出验证通过后，将参与该任务的源文件移动到 `Extra`。

- 清理策略：

  ```bash
  plexmuxy mux /path/to/media --cleanup none
  plexmuxy mux /path/to/media --cleanup move --extra-dir Extra
  plexmuxy mux /path/to/media --cleanup delete --yes
  ```

  删除必须显式传入 `--yes`。mux 失败或输出验证失败时不会执行清理。

- 输出命名：

  ```bash
  plexmuxy mux /path/to/media --output-suffix _Plex
  plexmuxy mux /path/to/media --output-dir PlexReady --name-strategy same-name
  plexmuxy mux /path/to/media --name-strategy template --name-template "{stem}.plex.mkv"
  ```

- 桌面 GUI：

  ```bash
  plexmuxy-gui
  plexmuxy gui
  ```

  GUI 使用 pywebview 和本地 HTML/CSS/JavaScript，并调用与 `plexmuxy plan`、`plexmuxy mux` 相同的核心 service。Windows 下会使用 Edge Chromium WebView2 Runtime。PlexMuxy 不内置 Fixed Version WebView2 Runtime；如果系统缺失，请从 [Microsoft WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) 安装 Evergreen Runtime。

- 打包：

  ```bash
  pip install -e ".[build]"
  pyinstaller plexmuxy-cli.spec
  pyinstaller plexmuxy-gui.spec
  ```

  CLI spec 会排除 `plexmuxy_gui`、`pywebview` 和未使用的 GUI 后端。GUI spec 会包含 `plexmuxy_gui/static`，并排除未使用的 Qt/CEF 后端。

- 常见错误：

  - `mkvmerge was not found`：安装 MKVToolNix、加入 `PATH`，或设置 `mkvmerge.path`。
  - `WebView2 Runtime`：从 Microsoft 安装 Evergreen Runtime。
  - `Delete cleanup requires --yes`：CLI 使用 `--yes`，GUI 中确认 delete cleanup。
  - `Output file already exists`：更换输出策略或启用 overwrite。

- **保证你的需要打包文件符合脚本所期待的命名规范**

  - 包含完整原始 `mkv` 文件名的文件会被考虑为同一组文件

    - 比如

      - `[Kamigami] Ansatsu Kyoushitsu [00][Ma10p_1080p][x265_flac].mkv` 和 `[Kamigami&VCB-Studio] Ansatsu Kyoushitsu [00][Ma10p_1080p][x265_flac].sc.ass` 为同一组资源

      - `[VCB-Studio] Tenki no Ko [Ma10p_2160p_HDR][x265_flac].mka`和`[VCB-Studio] Tenki no Ko [Ma10p_2160p_HDR][x265_flac].mkv` 为同一组资源

    - 在此基础上，会在文件名中查找关键字串符，以匹配字幕资源。规则如下表，脚本判断顺序为该表从上至下

      |                        关键字串符                        | 判断结果 |
      | :------------------------------------------------------: | :------: |
      | `.jpsc`, `[jpsc]`, `jp_sc`, `[jp_sc]`, `chs&jap`, `简日` |   简日   |
      | `.jptc`, `[jptc]`, `jp_tc`, `[jp_tc]`, `cht&jap`, `繁日` |   繁日   |
      |      `.chs`, `.sc`, `[chs]`, `[sc]`, `.gb`, `[gb]`       |   简中   |
      |     `.cht`, `.tc`, `[cht]`, `[tc]`, `big5`, `[big5]`     |   繁中   |
      |     `.jp`, `.jpn`, `.jap`, `[jp]`, `[jpn]`, `[jap]`      |   日语   |

    - 文件名的第一个字符若为 `[`，则会匹配所有随后的内容直至下一个`]` ，作为字幕作者名称并添加进轨道名称

      - 比如
        - `[Kamigami] Ansatsu Kyoushitsu [00][Ma10p_1080p][x265_flac].sc.as`的作者为 `Kamigami&VCB-Studio`，该字幕轨道名称为` chs Kamigami&VCB-Studio`

  - 若没有找到同一组资源文件，则会在原始 `mkv` 文件中寻找 `[01]` 这样的剧集数关键词，即被`[` 和 `]`包围的两位数字

    - 随后使用该剧集数在整个工作目录中寻找包含相同数字的文件，这些文件中的数字必须符合以下的规则才会被读取（以 `[02]` 为例）：
      - `[02]`
      - `.02.`
      - ` 02 ` (前后分别有一个空格)
      - `02.`（前面有一个空格）

  - 若工作路径下有一个名为 `Fonts`的目录，则会该目录中所有字体文件，不会再有额外的操作

    - `ttf`, `otf `和 `ttc` 格式文件被视为有效的字体

  - 若工作路径下没有名为 `Fonts`的目录，则会将工作路径下文件名包含 `Fonts` 关键词的 `zip`和 `7z` 文件解压，使用其中的字体文件作为附加字体

## 效果预览

### 程序运行

![](https://github.com/Masterain98/Repo-README-Images/blob/main/Anime-MKV-Plex-Packager/Cli-sample.png?raw=true)

### Plex 字幕选择

![](https://raw.githubusercontent.com/Masterain98/Repo-README-Images/main/Anime-MKV-Plex-Packager/Plex-sample-sub-options.png)
