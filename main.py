import os
import sys
import shutil
import subprocess
from pymkv import MKVFile, MKVTrack
import py7zr
import re
import patoolib
import gettext
#import locale
import zlib
import logging
from datetime import datetime
from multiprocessing.pool import ThreadPool
from rich.progress import Progress
from tkinter import filedialog
from pathlib import Path
from config import get_config
from compressed import unzip
from subtitle_utils import subtitle_info_checker, is_font_file

# l10n

"""lang_settings = locale.getlocale()
bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
locales_dir = os.path.abspath(os.path.join(bundle_dir, 'locales'))
if "Chinese" in lang_settings[0]:
    lang_set = ["zh-CN"]
else:
    lang_set = ["en-US"]
language_translations = gettext.translation("base", localedir=locales_dir, languages=lang_set)
language_translations.install()
_ = language_translations.gettext"""
# Global Variable
try:
    config = get_config()
except ValueError:
    input("Config file error, press ENTER to exit")
    exit(0)
DELETE_FONTS = config["TaskSettings"]["DeleteFonts"]
DELETE_ORIGINAL_MKV = config["TaskSettings"]["DeleteOriginalMKV"]
DELETE_ORIGINAL_MKA = config["TaskSettings"]["DeleteOriginalMKA"]
DELETE_SUB = config["TaskSettings"]["DeleteSubtitle"]
SUFFIX_NAME = config["TaskSettings"]["OutputSuffixName"]
UNRAR_PATH = config["Font"]["Unrar_Path"]
T_COUNT = config["multiprocessing"]["thread_count"]
if SUFFIX_NAME == "":
    SUFFIX_NAME = "_Plex"
if config["mkvmerge"]["path"] != "":
    MKVMERGE_PATH = config["mkvmerge"]["path"]
else:
    print("mkvmerge path not set, using mkvmerge.exe in the working directory")
    MKVMERGE_PATH = "mkvmerge"
if type(T_COUNT) is str:
    if T_COUNT.isnumeric():
        T_COUNT = int(T_COUNT)
    elif T_COUNT.lower() == "auto":
        T_COUNT = os.cpu_count()
    else:
        T_COUNT = 1
task_pool = ThreadPool(processes=T_COUNT)
logging.basicConfig(filename=os.path.expandvars("%userprofile%/Documents/PlexMuxy/%s.log") % datetime.now().
                    strftime("%Y%m%d-%H%M%S"), encoding="utf-8", level=logging.DEBUG,
                    format="%(levelname)s:%(asctime)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def mkv_mux_task(mkv_file_name: str, folder_other_file_list: list, font_list: list,
                 major_progress: Progress, major_process_task) -> dict:
    # Initial variables
    this_ep_num = "default"
    skip_this_task = True
    this_delete_list = []
    this_move_list = []
    sub_track_count = 0

    if SUFFIX_NAME not in mkv_file_name:
        # Generate the task with MKV file
        major_progress.console.print(f"[orange]Task start: {mkv_file_name}")
        mkv_name_no_extension = mkv_file_name.replace(".mkv", "")
        this_task = MKVFile(mkv_file_name, mkvmerge_path=MKVMERGE_PATH)
        for track in this_task.tracks:
            sub_track_count += 1
            if track.track_type == "audio" or track.track_type == "subtitles":
                if track.language == "und":
                    logging.warning("Track %s (%s track) language is undefined, set a language for it" % (
                        track.track_id, track.track_type))
                    track.language_ietf = input("Input a language code for this track"
                                                " (zh-Hans/zh-Hant/jp/en/ru or other language code): ")

        if DELETE_ORIGINAL_MKV:
            this_delete_list.append(mkv_file_name)
        else:
            this_move_list.append(mkv_file_name)

        # Episode name
        ep_romaji_name = re.sub(r"\[(?!\d+\]).*?\]", "", mkv_name_no_extension).strip()
        print(f"Episode name: {ep_romaji_name}")

        for item in folder_other_file_list:
            # Match resources based on file name
            item_name_no_extension = Path(item).stem
            item_romaji_name = re.sub(r"\[(?!\d+\]).*?\]", "", item_name_no_extension).strip()
            if mkv_name_no_extension in item or ep_romaji_name in item_romaji_name:
                print(f"Find associated file with same name: {item}")
                if item.endswith(".ass"):
                    # Add Subtitle track
                    sub_track_count += 1
                    this_sub_info = subtitle_info_checker(item)
                    logging.info("Subtitle info: " + str(this_sub_info))
                    if this_sub_info["language"] != "":
                        if config["Subtitle"]["ShowSubtitleAuthorInTrackName"]:
                            track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                        else:
                            track_name = this_sub_info["language"]
                        if this_sub_info["default_language"]:
                            this_default_track = True
                            this_forced_track = True
                        else:
                            this_default_track = False
                            this_forced_track = False
                        this_task.add_track(MKVTrack(item, track_name=track_name, default_track=this_default_track,
                                                     language=this_sub_info["mkv_language"],
                                                     language_ietf=this_sub_info["ietf_language"],
                                                     mkvmerge_path=MKVMERGE_PATH, forced_track=this_forced_track,
                                                     ))
                        skip_this_task = False
                        logging.info("Find " + this_sub_info["language"] + " subtitle: " + item)

                        if DELETE_SUB:
                            this_delete_list.append(item)
                        else:
                            this_move_list.append(item)
                if item.endswith(".mka"):
                    # Add MKA track
                    skip_this_task = False
                    this_task.add_track(item)
                    logging.info("Find associated audio: " + item)
                    if DELETE_ORIGINAL_MKA:
                        this_delete_list.append(item)
                    else:
                        this_move_list.append(item)
            else:
                # Expand the search range for other subgroups
                # By matching up the episode number
                this_ep_num = re.search(r'(\[)(SP|sp)?(\d{2})(])', mkv_name_no_extension)
                if this_ep_num is None:
                    this_ep_num = re.search(r'(\[)(Special)|(OVA)(])', mkv_name_no_extension)
                if this_ep_num is not None:
                    this_ep_num = this_ep_num.group(0)
                    sub_matched = False
                    if this_ep_num in item and item != mkv_file_name:
                        # this_ep_num = [01]
                        sub_matched = True
                    elif this_ep_num.replace("[", " ").replace("]", " ") in item and item != mkv_file_name:
                        # this_ep_num =  01 (one space before and after the number)
                        sub_matched = True
                    elif this_ep_num.replace("[", ".").replace("]", ".") in item and item != mkv_file_name:
                        # this_ep_num =  .01. (one dot before and after the number)
                        sub_matched = True
                    elif this_ep_num.replace("[", " ").replace("]", ".") in item and item != mkv_file_name:
                        # this_ep_num =  01. (one space before and one dot after the number)
                        sub_matched = True
                    if sub_matched:
                        logging.info("Using ep number " + this_ep_num + " to match subtitle file")
                        if item.endswith(".ass"):
                            sub_track_count += 1
                            this_sub_info = subtitle_info_checker(item)
                            # this_progress.console.print(this_sub_info)
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
                                    this_sub_track.forced_track = True
                                skip_this_task = False
                                this_task.add_track(this_sub_track)
                                logging.info("Find " + this_sub_info["language"] + " subtitle: " + item)

                                if DELETE_SUB:
                                    this_delete_list.append(item)
                                else:
                                    this_move_list.append(item)

        if sub_track_count == 0:
            this_ep_num = "main movie"
            # No episode number found, most likely a movie, include all ass files
            logging.info("No EP number found, use movie mode")
            all_ass_files = [file for file in folder_other_file_list if file.endswith(".ass")]
            for sub_file in all_ass_files:
                this_sub_info = subtitle_info_checker(sub_file)
                if this_sub_info["language"] != "":
                    if config["Subtitle"]["ShowSubtitleAuthorInTrackName"]:
                        track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                    else:
                        track_name = this_sub_info["language"]
                    this_sub_track = MKVTrack(sub_file, track_name=track_name, default_track=False,
                                              language=this_sub_info["mkv_language"],
                                              language_ietf=this_sub_info["ietf_language"],
                                              mkvmerge_path=MKVMERGE_PATH)
                    if this_sub_info["default_language"]:
                        this_sub_track.default_track = True
                        this_sub_track.forced_track = True
                    skip_this_task = False
                    this_task.add_track(this_sub_track)
                    logging.info("Find " + this_sub_info["language"] + " subtitle: " + sub_file)
                    if DELETE_SUB:
                        this_delete_list.append(sub_file)
                    else:
                        this_move_list.append(sub_file)

        # Check all tracks, if only one subtitle track, then mark it as default
        if sub_track_count == 1:
            for track in this_task.tracks:
                if track.track_type == "subtitles":
                    track.default_track = True
                    try:
                        logging.info("Set default subtitle track: " + track.track_name)
                    except TypeError:
                        logging.info("Set default subtitle track: " + "None")
        # Add fonts
        for font in font_list:
            font = "Fonts/" + font
            this_task.add_attachment(font)
        if not skip_this_task:
            task_progress_name = "EP " + str(this_ep_num) + " Task"
            this_task_progress = major_progress.add_task(task_progress_name, total=None, visible=True)
            new_mkv_name = mkv_name_no_extension + SUFFIX_NAME + ".mkv"
            this_task.mux(new_mkv_name, silent=True, ignore_warning=True)
            major_progress.console.print("[green]Mux successfully: " + new_mkv_name)
            major_progress.console.print("MKVMerge raised error: " + new_mkv_name)
            major_progress.update(major_process_task, advance=1, visible=True)
            major_progress.update(this_task_progress, completed=True, visible=False)
        else:
            major_progress.console.print("No task for this MKV" + mkv_file_name)
    return {"delete_list": this_delete_list, "move_list": this_move_list}


def main():
    delete_list = []
    move_list = []

    folder_selected = filedialog.askdirectory()
    os.chdir(folder_selected)
    logging.info("Using working directory: " + os.getcwd())
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
                print("Find font package file: " + file_name)
                logging.info("Find font package file: " + file_name)
                if not os.path.exists("Fonts"):
                    os.makedirs("Fonts")
                    print("Fonts sub-directory created")
                    logging.info("Fonts sub-directory created")
                if ".zip" in file_name:
                    # zip extension
                    try:
                        unfiltered_font_list = unzip(file_name, "utf-8")
                        print("Unzipped to /Fonts: " + str(unfiltered_font_list))
                        logging.info("Unzipped to /Fonts: " + str(unfiltered_font_list))
                    except UnicodeDecodeError:
                        print("Unsupported encoding, please manually zip the file")
                        logging.error("Unsupported encoding, please manually zip the file")
                        exit(0)
                    except zlib.error:
                        print("Unsupported encoding, please manually zip the file")
                        logging.error("Unsupported encoding, please manually zip the file")
                        exit(0)
                elif ".7z" in file_name:
                    # 7z extension
                    with py7zr.SevenZipFile(file_name, mode='r') as z:
                        z.extractall("Fonts")
                        unfiltered_font_list = z.getnames()
                        print("Unzipped to /Fonts: " + str(unfiltered_font_list))
                        logging.info("Unzipped to /Fonts: " + str(unfiltered_font_list))
                elif ".rar" in file_name:
                    if UNRAR_PATH != "":
                        patoolib.extract_archive(file_name, outdir="./Fonts/", program=UNRAR_PATH)
                        unfiltered_font_list = os.listdir("Fonts")
                    else:
                        print("Unrar path not set, please manually unrar the file")
                        logging.error("Unrar path not set, please manually unrar the file")
                else:
                    print("%s is an unrecognized compressed file format, please manually unzip the file" % file_name)
                    logging.error(
                        "%s is an unrecognized compressed file format, please manually unzip the file" % file_name)
                print("=" * 20)
    # Filter fonts file
    font_list = list(filter(is_font_file, unfiltered_font_list))
    print("Loading fonts: " + str(font_list))

    # Generate two useful list to reduce chance traversing folder_list in main task loop
    folder_mkv_list = [file for file in folder_list if file.endswith(".mkv")]
    folder_other_file_list = [file for file in folder_list if not file.endswith(".mkv") and "." in file]

    with Progress() as progress:
        main_task_progress = progress.add_task("[green]Main task", total=len(folder_mkv_list), visible=True)
        async_results = [task_pool.apply_async(mkv_mux_task, args=(mkv_file_name, folder_other_file_list, font_list,
                                                                   progress, main_task_progress))
                         for mkv_file_name in folder_mkv_list]
        results = [ar.get() for ar in async_results]
        for result in results:
            delete_list.extend(result["delete_list"])
            move_list.extend(result["move_list"])

    try:
        # Clean up
        extra_folder_is_exist = os.path.exists("Extra")
        if not extra_folder_is_exist and len(move_list) >= 1:
            os.makedirs("Extra")
        if DELETE_FONTS:
            try:
                shutil.rmtree("Fonts/")
                print("Remove Fonts Folder Successfully")
                logging.info("Remove Fonts Folder Successfully")
            except OSError:
                print("Remove Fonts Folder Error")
                logging.error("Remove Fonts Folder Error")
        for file in delete_list:
            try:
                os.remove(file)
            except OSError:
                print("Failed to delete " + file)
                logging.error("Failed to delete " + file)
        for file in move_list:
            shutil.move(file, "Extra/" + file)
        logging.info("Task finished")
        input("Task finished. Press Enter to exit...")
    except Exception as e:
        print(e)
        input("Error at clean up stage. Press Enter to exit")
        logging.error(e)


if __name__ == '__main__':
    main()
