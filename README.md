# Anime-MKV-Plex-Packager
A Python script to allow Plex load CN-Subs Anime MKV 

### Feature

- Merge original MKV video with subtitles, subtitle fonts and external audio tracks to meet requirements of Plex server
  - Simplified-Chinese will be added as ```chi``` language and the track will be named as ```chs```
  - Traditional Chinese will be added as ```chi``` language and the track will be named as ```cht```
  - Subtitle fonts will be added as attachment and Plex will load them automictically
  - External audio tracks (usually 5.1 Channel) will be added and keep original track information
- (Optional) Rename or remove original files
  - Rename mode will add ```.bak``` at the end of file name
- The new generated MKV file will be automatically added a suffix name 
  - Can be changed in settings
  - Default as ```_Plex```
- A friendly reminder that the encoding and subtitling groups distribute the multi-channel audio and font files separately to save storage space, and that running this script increases the storage space used by the episodes, a change that is sometimes significant.

### How to  Use

- Install [MKVToolNix](https://mkvtoolnix.download/) and add it to System Path

  - Or, always copy a ```mkvmerge.exe``` with ```main.py``` together

- Copy ```main.py``` to the anime series folder

  - Change the setting in the ```Global Variables``` parts

  - Default settings are:

    ```python
    # Global Variable
    DELETE_FONTS = True
    DELETE_ORIGINAL_MKV = False
    RENAME_ORIGINAL_MKV = True
    DELETE_ORIGINAL_MKA = False
    RENAME_ORIGINAL_MKA = True
    DELETE_CHS_SUB = False
    RENAME_CHS_SUB = True
    DELETE_CHT_SUB = False
    RENAME_CHT_SUB = True
    SUFFIX_NAME = "_Plex"
    ```

- Make sure all associated content has same name with each corresponding episode

  - ```sc.ass``` and ```chs.ass``` are considered as Simplified-Chinese subtitle
  - ```tc.ass``` and ```cht.ass`` are considered as Transitional-Chinese subtitle
  - The rules are mostly following VCB-Studio naming rules

- Run ```main.py``` in the Command Line

### Example

- Here's an example in which files will be considered as a group

```powershell
PS D:\Downloads\[Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p]> python main.py
Find associated CHS subtitle: [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].chs_v2.ass
Find associated CHT subtitle: [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].cht_v2.ass
Find associated audio: [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].mka
Find main video: [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].mkv
Running with command:
"mkvmerge -o [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac]_Plex.mkv --language 0:und --default-track 0:1 --forced-track 0:0 -d 0 -A -S [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].mkv --language 1:jpn --default-track 1:1 --forced-track 1:0 -D -a 1 -S [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].mkv --track-name 0:chs --language 0:chi --default-track 0:1 --forced-track 0:0 -D -A -s 0 [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].chs_v2.ass --track-name 0:cht --language 0:chi --default-track 0:0 --forced-track 0:0 -D -A -s 0 [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].cht_v2.ass --default-track 0:0 --forced-track 0:0 -D -a 0 -S [Mabors-Sub&Kamigami&KTXP&VCB-Studio] Saenai Heroine no Sodatekata Fine [Ma10p_1080p][x265_flac].mka"
====================
Task finished. Press any key to exit...
```



