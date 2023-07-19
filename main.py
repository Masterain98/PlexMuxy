import os
import shutil
import subprocess
from pymkv import MKVFile, MKVTrack
import py7zr
import re
import patoolib
import gettext
import locale
from config import get_config
from compressed import unzip
from subtitle_utils import subtitle_info_checker, is_font_file

# Global Variable
# i10n
lang_settings = locale.getlocale()
if "Chinese" in lang_settings[0]:
    lang_set = ["zh-CN"]
else:
    lang_set = ["en"]
language_translations = gettext.translation("base", localedir="locales", languages=lang_set)
language_translations.install()
_ = language_translations.gettext
try:
    config = get_config()
except ValueError:
    input(_("Config file error, press ENTER to exit"))
    exit(0)
DELETE_FONTS = config["TaskSettings"]["DeleteFonts"]
DELETE_ORIGINAL_MKV = config["TaskSettings"]["DeleteOriginalMKV"]
DELETE_ORIGINAL_MKA = config["TaskSettings"]["DeleteOriginalMKA"]
DELETE_SUB = config["TaskSettings"]["DeleteSubtitle"]
SUFFIX_NAME = config["TaskSettings"]["OutputSuffixName"]
UNRAR_PATH = config["Font"]["Unrar_Path"]
if SUFFIX_NAME == "":
    SUFFIX_NAME = "_Plex"
if config["mkvmerge"]["path"] != "":
    MKVMERGE_PATH = config["mkvmerge"]["path"]
else:
    print(_("mkvmerge path not set, using mkvmerge.exe in the working directory"))
    MKVMERGE_PATH = "mkvmerge"


def main():
    delete_list = []
    move_list = []

    custom_workdir = input(_("Please input the working directory (default: current directory): "))
    if custom_workdir != "":
        os.chdir(custom_workdir)
    folder_list = os.listdir()

    # Prepare fonts
    # If Fonts folder exists, load all fonts in it
    if os.path.exists("Fonts"):
        unfiltered_font_list = os.listdir("Fonts")
    else:
        # If Fonts folder does not exist
        unfiltered_font_list = []
        for file_name in folder_list:
            # if there is a zipped fonts file, unzip it
            if "font" in file_name.lower():
                print(_("Find font package file: ") + file_name)
                if not os.path.exists("Fonts"):
                    os.makedirs("Fonts")
                    print(_("Fonts sub-directory created"))
                if ".zip" in file_name:
                    # zip extension
                    try:
                        unfiltered_font_list = unzip(file_name, "utf-8")
                        print(_("Unzipped to /Fonts: ") + str(unfiltered_font_list))
                    except UnicodeDecodeError:
                        print(_("Unsupported encoding, please manually zip the file"))
                        exit(0)
                elif ".7z" in file_name:
                    # 7z extension
                    with py7zr.SevenZipFile(file_name, mode='r') as z:
                        z.extractall("Fonts")
                        unfiltered_font_list = z.getnames()
                        print(_("Unzipped to /Fonts: ") + str(unfiltered_font_list))
                elif ".rar" in file_name:
                    if UNRAR_PATH != "":
                        patoolib.extract_archive(file_name, outdir="./Fonts/", program=UNRAR_PATH)
                        unfiltered_font_list = os.listdir("Fonts")
                    else:
                        print(_("Unrar path not set, please manually unrar the file"))
                else:
                    print(_("%s is an unrecognized compressed file format, please manually unzip the file") % file_name)
                print("=" * 20)
    # Filter fonts file
    font_list = list(filter(is_font_file, unfiltered_font_list))
    print(_("Loading fonts: ") + str(font_list))

    # Generate two useful list to reduce chance traversing folder_list in main task loop
    folder_mkv_list = [file for file in folder_list if file.endswith(".mkv")]
    folder_other_file_list = [file for file in folder_list if not file.endswith(".mkv") and "." in file]

    # Main tasks
    # Traverse all MKV files (videos) in folder
    for MKV_file_name in folder_mkv_list:
        # Initial variables
        skip_this_task = True

        if SUFFIX_NAME not in MKV_file_name:
            # Generate the task with MKV file
            print(_("Task start: ") + MKV_file_name)
            mkv_name_no_extension = MKV_file_name.replace(".mkv", "")
            this_task = MKVFile(MKV_file_name, mkvmerge_path=MKVMERGE_PATH)
            for track in this_task.tracks:
                if track.track_type == "audio" or track.track_type == "subtitles":
                    if track.language == "und":
                        print(_("Track %s (%s track) language is undefined, set a language for it")
                              % (track.track_id, track.track_type))
                        track.language_ietf = input(_("Input a language code for this track"
                                                      " (zh-Hans/zh-Hant/jp/en/ru or other language code): "))

            if DELETE_ORIGINAL_MKV:
                delete_list.append(MKV_file_name)
            else:
                move_list.append(MKV_file_name)

            for item in folder_other_file_list:
                # Match resources based on file name
                if mkv_name_no_extension in item:
                    if item.endswith(".ass"):
                        # Add Subtitle track
                        this_sub_info = subtitle_info_checker(item)
                        print(_("Subtitle info: ") + str(this_sub_info))
                        if this_sub_info["language"] != "":
                            if config["Subtitle"]["ShowSubtitleAuthorInTrackName"]:
                                track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                            else:
                                track_name = this_sub_info["language"]
                            this_sub_track = MKVTrack(item, track_name=track_name, default_track=False,
                                                      language=this_sub_info["mkv_language"],
                                                      language_ietf=this_sub_info["ietf_language"],
                                                      mkvmerge_path=MKVMERGE_PATH)
                            if this_sub_info["default_language"]:
                                this_sub_track.default_track = True
                            skip_this_task = False
                            this_task.add_track(this_sub_track)
                            print(_("Find ") + this_sub_info["language"] + _(" subtitle: ") + item)

                            if DELETE_SUB:
                                delete_list.append(item)
                            else:
                                move_list.append(item)
                    if item.endswith(".mka"):
                        # Add MKA track
                        skip_this_task = False
                        this_task.add_track(item)
                        print(_("Find associated audio: ") + item)
                        if DELETE_ORIGINAL_MKA:
                            delete_list.append(item)
                        else:
                            move_list.append(item)
                else:
                    # Expand the search range for other subgroups
                    # By matching up the episode number
                    this_ep_num = re.search(r'(\[)(SP|sp)?(\d{2})(])', mkv_name_no_extension)
                    if this_ep_num is not None:
                        this_ep_num = this_ep_num.group(0)
                        sub_matched = False
                        if this_ep_num in item and item != MKV_file_name:
                            # this_ep_num = [01]
                            sub_matched = True
                        elif this_ep_num.replace("[", " ").replace("]", " ") in item and item != MKV_file_name:
                            # this_ep_num =  01 (one space before and after the number)
                            sub_matched = True
                        elif this_ep_num.replace("[", ".").replace("]", ".") in item and item != MKV_file_name:
                            # this_ep_num =  .01. (one dot before and after the number)
                            sub_matched = True
                        elif this_ep_num.replace("[", " ").replace("]", ".") in item and item != MKV_file_name:
                            # this_ep_num =  01. (one space before and one dot after the number)
                            sub_matched = True
                        if sub_matched:
                            print(_("Using ep number ") + this_ep_num + _(" to match subtitle file"))
                            if item.endswith(".ass"):
                                this_sub_info = subtitle_info_checker(item)
                                print(this_sub_info)
                                if this_sub_info["language"] != "":
                                    if config["Subtitle"]["ShowSubtitleAuthorInTrackName"]:
                                        track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                                    else:
                                        track_name = this_sub_info["language"]
                                    this_sub_track = MKVTrack(item, track_name=track_name, default_track=False,
                                                              language=this_sub_info["mkv_language"],
                                                              language_ietf=this_sub_info["ietf_language"],
                                                              mkvmerge_path=MKVMERGE_PATH)
                                    if this_sub_info["default_language"]:
                                        this_sub_track.default_track = True
                                    skip_this_task = False
                                    this_task.add_track(this_sub_track)
                                    print(_("Find ") + this_sub_info["language"] + _(" subtitle: ") + item)

                                    if DELETE_SUB:
                                        delete_list.append(item)
                                    else:
                                        move_list.append(item)
            for font in font_list:
                font = "Fonts/" + font
                this_task.add_attachment(font)
            if not skip_this_task:
                new_mkv_name = mkv_name_no_extension + SUFFIX_NAME + ".mkv"
                try:
                    print("")
                    this_task.mux(new_mkv_name, silent=True)
                    print(_("Mux successfully: ") + new_mkv_name)
                except subprocess.CalledProcessError:
                    # A mysterious error will not cause any problem
                    print(_("MKVMerge raised error: ") + new_mkv_name)
                print("=" * 20)
            else:
                print(_("No task for this MKV"))

    try:
        # Clean up
        extra_folder_is_exist = os.path.exists("Extra")
        if not extra_folder_is_exist and len(move_list) >= 1:
            os.makedirs("Extra")
        if DELETE_FONTS:
            try:
                shutil.rmtree("Fonts/")
                print(_("Remove Fonts Folder Successfully"))
            except OSError:
                print(_("Remove Fonts Folder Error"))
        for file in delete_list:
            try:
                os.remove(file)
            except OSError:
                print(_("Failed to delete ") + file)
        for file in move_list:
            shutil.move(file, "Extra/" + file)

        input(_("Task finished. Press Enter to exit..."))
    except Exception as e:
        print(e)
        input(_("Error at clean up stage. Press Enter to exit"))


if __name__ == '__main__':
    main()
