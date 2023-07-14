import os
import shutil
import subprocess
import time
from pymkv import MKVFile, MKVTrack
import py7zr
import re
from config import get_config
from compressed import unzip
from subtitle_utility import subtitle_info_checker, is_font_file

# Global Variable
try:
    config = get_config()
except ValueError:
    exit(0)
DELETE_FONTS = config["TaskSettings"]["DeleteFonts"]
DELETE_ORIGINAL_MKV = config["TaskSettings"]["DeleteOriginalMKV"]
DELETE_ORIGINAL_MKA = config["TaskSettings"]["DeleteOriginalMKA"]
DELETE_SUB = config["TaskSettings"]["DeleteSubtitle"]
SUFFIX_NAME = config["TaskSettings"]["OutputSuffixName"]
if SUFFIX_NAME == "":
    SUFFIX_NAME = "_Plex"
if config["mkvmerge"]["path"] != "":
    MKVMERGE_PATH = config["mkvmerge"]["path"]
else:
    print("mkvmerge path not set, using mkvmerge.exe in the working directory")
    MKVMERGE_PATH = "mkvmerge"


if __name__ == '__main__':
    delete_list = []
    move_list = []

    custom_workdir = input("Please input the working directory (default: current directory): ")
    if custom_workdir != "":
        os.chdir(custom_workdir)
    folder_list = os.listdir()

    # Prepare fonts
    font_list = []
    # If Fonts folder exists, load all fonts in it
    if os.path.exists("Fonts"):
        unfiltered_font_list = os.listdir("Fonts")
    else:
        # If Fonts folder does not exist
        unfiltered_font_list = []
        for file_name in folder_list:
            # if there is a zipped fonts file, unzip it
            if "font" in file_name.lower() and ".zip" in file_name:
                # zip extension
                print("Find font package file: " + file_name)
                if not os.path.exists("Fonts"):
                    os.makedirs("Fonts")
                    print("Fonts sub-directory created")
                unfiltered_font_list = unzip(file_name, "cp437")
                print("Unzipped to /Fonts: " + str(unfiltered_font_list))
                print("=" * 20)
            elif "Font" in file_name and ".7z" in file_name:
                # 7z extension
                print("Find font package file: " + file_name)
                if not os.path.exists("Fonts"):
                    os.makedirs("Fonts")
                    print("Fonts sub-directory created")
                with py7zr.SevenZipFile(file_name, mode='r') as z:
                    z.extractall("Fonts")
                    unfiltered_font_list = z.getnames()
                    print("Unzipped to /Fonts: " + str(unfiltered_font_list))
    # Filter fonts file
    font_list = list(filter(is_font_file, unfiltered_font_list))
    print("Loading fonts: " + str(font_list))

    # Generate two useful list to reduce chance traversing folder_list in main task loop
    folder_mkv_list = [file for file in folder_list if file.endswith(".mkv")]
    folder_other_file_list = [file for file in folder_list if not file.endswith(".mkv") and "." in file]

    # input("waiting...")
    # Main tasks
    # Traverse all MKV files (videos) in folder
    for MKV_file_name in folder_mkv_list:
        # Initial variables
        skip_this_task = True

        if SUFFIX_NAME not in MKV_file_name:
            # Generate the task with MKV file
            print("Task start: " + MKV_file_name)
            MKV_name_no_extension = MKV_file_name.replace(".mkv", "")
            this_task = MKVFile(MKV_file_name, mkvmerge_path=MKVMERGE_PATH)

            if DELETE_ORIGINAL_MKV:
                delete_list.append(MKV_file_name)
            else:
                move_list.append(MKV_file_name)

            for item in folder_other_file_list:
                # Match resources based on file name
                if MKV_name_no_extension in item:
                    if item.endswith(".ass"):
                        # Add Subtitle track
                        this_sub_info = subtitle_info_checker(item)
                        print("Subtitle info: " + str(this_sub_info))
                        if this_sub_info["language"] != "":
                            if config["Subtitle"]["ShowSubtitleAuthorInTrackName"]:
                                track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                            else:
                                track_name = this_sub_info["language"]
                            this_sub_track = MKVTrack(item, track_name=track_name,
                                                      default_track=False, language=this_sub_info["mkv_language"],
                                                      mkvmerge_path=MKVMERGE_PATH)
                            if this_sub_info["default_language"]:
                                this_sub_track.default_track = True
                            skip_this_task = False
                            this_task.add_track(this_sub_track)
                            print("Find " + this_sub_info["language"] + " subtitle: " + item)

                            if DELETE_SUB:
                                delete_list.append(item)
                            else:
                                move_list.append(item)
                    if item.endswith(".mka"):
                        # Add MKA track
                        skip_this_task = False
                        this_task.add_track(item)
                        print("Find associated audio: " + item)
                        if DELETE_ORIGINAL_MKA:
                            delete_list.append(item)
                        else:
                            move_list.append(item)
                else:
                    # Expand the search range for other subgroups
                    # By matching up the episode number
                    this_ep_num = re.search(r'(\[)(SP|sp)?(\d{2})(])', MKV_name_no_extension)
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
                            print("Using ep number " + this_ep_num + " to match subtitle file")
                            if item.endswith(".ass"):
                                this_sub_info = subtitle_info_checker(item)
                                print(this_sub_info)
                                if this_sub_info["language"] != "":
                                    if config["Subtitle"]["ShowSubtitleAuthorInTrackName"]:
                                        track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                                    else:
                                        track_name = this_sub_info["language"]
                                    this_sub_track = MKVTrack(item, track_name=track_name,
                                                              default_track=False,
                                                              language=this_sub_info["mkv_language"],
                                                              mkvmerge_path=MKVMERGE_PATH)
                                    if this_sub_info["default_language"]:
                                        this_sub_track.default_track = True
                                    skip_this_task = False
                                    this_task.add_track(this_sub_track)
                                    print("Find " + this_sub_info["language"] + " subtitle: " + item)

                                    if DELETE_SUB:
                                        delete_list.append(item)
                                    else:
                                        move_list.append(item)
            # input("waiting...")
            for font in font_list:
                font = "Fonts/" + font
                this_task.add_attachment(font)
            if not skip_this_task:
                newMKV_name = MKV_name_no_extension + SUFFIX_NAME + ".mkv"
                try:
                    print("")
                    this_task.mux(newMKV_name, silent=True)
                    print("Mux successfully: " + newMKV_name)
                except subprocess.CalledProcessError as e:
                    # A mysterious error will not cause any problem
                    print("MKVMerge raised error: " + newMKV_name)
                print("=" * 20)
            else:
                print("No task for this MKV")

    try:
        # Clean up
        ExtraFolderIsExists = os.path.exists("Extra")
        if not ExtraFolderIsExists and len(move_list) >= 1:
            os.makedirs("Extra")
        if DELETE_FONTS:
            try:
                shutil.rmtree("Fonts/")
                print("Remove Fonts Folder Successfully")
            except OSError:
                print("Remove Fonts Folder Error")
        for file in delete_list:
            try:
                os.remove(file)
            except OSError:
                print("Failed to delete " + file)
        for file in move_list:
            shutil.move(file, "Extra/" + file)

        input("Task finished. Press Enter to exit...")
    except Exception as e:
        print(e)
        input("Error at clean up stage. Press Enter to exit...")
