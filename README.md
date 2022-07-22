# PlexMuxy
PlexMuxy is a Python script to multiplex video with each independent audio, subtitle and fonts in bulk, in order to allow Plex Media Server to present media best in visual. 

English README | [中文 README](https://github.com/Masterain98/PlexMuxy/blob/main/README.CN.md)

## Feature

- Mux `mkv` video, `mka` audio, `ass` subtitles, and fonts together into a single `mkv` file
  - Audio
    - Usually are external 5.1 Channel audio and audio commentary

  - Subtitle
    - Determine the language by file name, including Simplified Chinese, Traditional Chinese, Japanese, SC&JP, TC&JP
      - For Simplified Chinese, track name will be `chs` , and language is marked as `chi`
      - For Traditional Chinese, track name will be `cht`, and language is marked as `chi`
      - For Japanese, track name will be `jpn` and language is marked as `jpn`
      - For SC&JP, track name will be `jp_sc` and language is marked as `chi`
      - For TC&JP, track name will be `jp_tc` and language is marked as `chi`

    - Determine the subtitle author by file name

  - Fonts
    - Fonts will be packaged together as attachments
    - This is designed to allow Plex to fully display the subtitle visual effect, but this is waste significant amount of storage. It is recommended to use font subset instead of full font file.

  - Based on user's setting, remove or move the original files to avoid Plex Server's scanning.


## Usage

- Download and install [MKVToolNix](https://mkvtoolnix.download/) and add its folder to `PATH ` system environment variables

  - Or, you can copy a `mkvmerge.exe` file to the same folder of `main.py`

- Take `main.py` into the work folder where media are stored

  - Change the `Global Variable` part setting with your own decision, default values are shown below:

    ```python
    # Global Variable
    DELETE_FONTS = False
    DELETE_ORIGINAL_MKV = False
    DELETE_ORIGINAL_MKA = False
    DELETE_SUB = False
    SUFFIX_NAME = "_Plex"
    ```

  - `DELETE_FONTS`
    - Delete `Fonts` subdirectory after the task is finished if `True`, otherwise do nothing
  - `DELETE_ORIGINAL_MKV`
    - Delete the original `mkv` file after the task is finished if `True`, otherwise move the file into `Extra` subdirectory

  - `DELETE_ORIGINAL_MKA` 
    - Delete the original `mka` file after the task is finished if `True`, otherwise move the file into `Extra` subdirectory

  - `DELETE_SUB`
    - Delete the original `ass` file after the task is finished if `True`, otherwise move the file into `Extra` subdirectory

  - `SUFFIX_NAME`
    - The suffix name in the new multiplexed, to differentiate with the original file; `_Plex` will be used as default if `SUFFIX_NAME = ""` 

- **Make sure the name of files used for mux meet the requirements**

  - File that name includes the original `mkv` file name is considered as the same group

    - e.g.

      - `[Kamigami] Ansatsu Kyoushitsu [00][Ma10p_1080p][x265_flac].mkv` and `[Kamigami&VCB-Studio] Ansatsu Kyoushitsu [00][Ma10p_1080p][x265_flac].sc.ass` are in the same group
      - `[VCB-Studio] Tenki no Ko [Ma10p_2160p_HDR][x265_flac].mka`and `[VCB-Studio] Tenki no Ko [Ma10p_2160p_HDR][x265_flac].mkv` are in the same group

    - Based on this rule, if the file is in `ass` extension, and there's key word matched, the language will be decided. The language decision rule is below in the table:

      - |                         Keywords                         | Decision |
        | :------------------------------------------------------: | :------: |
        | `.jpsc`, `[jpsc]`, `jp_sc`, `[jp_sc]`, `chs&jap`, `简日` |  jp_sc   |
        | `.jptc`, `[jptc]`, `jp_tc`, `[jp_tc]`, `cht&jap`, `繁日` |  jp_tc   |
        |      `.chs`, `.sc`, `[chs]`, `[sc]`, `.gb`, `[gb]`       |   chs    |
        |     `.cht`, `.tc`, `[cht]`, `[tc]`, `big5`, `[big5]`     |   cht    |
        |     `.jp`, `.jpn`, `.jap`, `[jp]`, `[jpn]`, `[jap]`      |   jpn    |

    - If the file name starts with `[`, and the following characters until next `]` will be considered as subtitle author and marked in the track name

      - e.g.
        - The author of `[Kamigami] Ansatsu Kyoushitsu [00][Ma10p_1080p][x265_flac].sc.as` is `Kamigami&VCB-Studio`，this subtitle track name will be ` chs Kamigami&VCB-Studio`

  - If there's no matching-up file, the program will find the episode number in `[02]` rule (number included by `[]`)

    - Then the program will match the file with same ep number, with the following rule
      - `[02]`
      - `.02.`
      - ` 02 ` (space before and after the ep number)
      - ` 02.` (One space before the ep number)

  - If there's a `Fonts` subdirectory, fonts in it will be used as attached fronts

    - Files only with `ttf`, `otf` and `ttc` extension are considered as fonts

  - If there isn't a `Fonts` subdirectory, the program will look for a `zip` or `7z` file including keyword `Fonts`, unzip it and use its contents as the attached fonts

- Run `main.py`

  - `python main.py`

## Screenshot

### Program running

![](https://github.com/Masterain98/Repo-README-Images/blob/main/Anime-MKV-Plex-Packager/Cli-sample.png?raw=true)

### Subtitle Choices from Plex 

![](https://raw.githubusercontent.com/Masterain98/Repo-README-Images/main/Anime-MKV-Plex-Packager/Plex-sample-sub-options.png)
