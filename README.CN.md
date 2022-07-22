# Plex 视频批量封装工具 (PlexMuxy)

PlexMuxy 是一个将字幕组/压制组发布作品进行封装的 Python 脚本，它会将外挂字幕、外挂音频、字幕字体文件进行打包，以允许 Plex 服务器能以最好的方法使用这些资源。

中文 README | [English README](https://github.com/Masterain98/PlexMuxy/blob/main/README.md)

## 功能和说明

- 将视频文件、音频文件、字幕文件和字体文件重新打包混流成一个`mkv` 格式的单文件
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

- 下载并安装 [MKVToolNix](https://mkvtoolnix.download/) 并添加其进入`PATH` 系统变量

  - 或者你也可以将一个  `mkvmerge.exe` 文件始终置于  `main.py` 的同目录下

- 将 `main.py` 放入到视频集所在目录

  - 修改 `Global Variable` 部分的变量值以修改设置，默认值如下：

    ```python
    # Global Variable
    DELETE_FONTS = False
    DELETE_ORIGINAL_MKV = False
    DELETE_ORIGINAL_MKA = False
    DELETE_SUB = False
    SUFFIX_NAME = "_Plex"
    ```

    - `DELETE_FONTS`
      - `True` 时在任务结束时删除 `Fonts` 文件夹，否则无操作

    - `DELETE_ORIGINAL_MKV`
      - `True` 时在任务结束时删除原始 `mkv` 文件，否则移动文件至 `Extra` 子目录中

    - `DELETE_ORIGINAL_MKA` 
      - `True` 时在任务结束时删除原始 `mka` 文件，否则移动文件至 `Extra` 子目录中

    - `DELETE_SUB`
      - `True` 时在任务结束时删除 `ass` 字幕文件，否则移动文件至 `Extra` 子目录中

    - `SUFFIX_NAME`
      - 在新的混流 `mkv` 文件结尾处添加的后缀文件名，用于标记本程序所创建的视频文件，若留空则会添加默认的 `_Plex` 后缀

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

- 运行 `main.py`

  - `python main.py`


## 效果预览

### 程序运行

![](https://github.com/Masterain98/Repo-README-Images/blob/main/Anime-MKV-Plex-Packager/Cli-sample.png?raw=true)

### Plex 字幕选择

![](https://raw.githubusercontent.com/Masterain98/Repo-README-Images/main/Anime-MKV-Plex-Packager/Plex-sample-sub-options.png)
