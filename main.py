import os
import shutil
import zipfile
from pymkv import MKVFile, MKVTrack
from pathlib import Path
import py7zr
import re

# Global Variable
DELETE_FONTS = False
DELETE_ORIGINAL_MKV = False
RENAME_ORIGINAL_MKV = True
DELETE_ORIGINAL_MKA = False
RENAME_ORIGINAL_MKA = True
DELETE_CHS_SUB = False
RENAME_CHS_SUB = True
DELETE_CHT_SUB = False
RENAME_CHT_SUB = True
SUFFIX_NAME = "_Plex"


# https://gist.github.com/hideaki-t/c42a16189dd5f88a955d
def unzip(f, encoding):
    font_list = []
    with zipfile.ZipFile(f) as z:
        for i in z.namelist():
            font_list.append("Fonts/" + i.encode('cp437').decode(encoding))
            n = Path("Fonts/" + i.encode('cp437').decode(encoding))
            if i[-1] == '/':
                if not n.exists():
                    n.mkdir()
            else:
                with n.open('wb') as w:
                    w.write(z.read(i))
    return font_list


def subtitle_info_checker(subtitle_file_name):
    # zh-CN
    chs_list = [".chs", ".sc", "[chs]", "[sc]", ".gb", "[gb]"]
    # zh-TW or zh-HK
    cht_list = [".cht", ".tc", "[cht]", "[tc]", "big5", "[big5]"]
    # Jpn and zh-CN
    jp_sc_list = [".jpsc", "[jpsc]", "jp_sc", "[jp_sc]", "chs&jap"]
    # Jpn and zh-TW/zh-HK
    jp_tc_list = [".jptc", "[jptc]", "jp_tc", "[jp_tc]", "cht&jap"]

    if any(indicator in subtitle_file_name.lower() for indicator in chs_list):
        language = "chs"
    elif any(indicator in subtitle_file_name.lower() for indicator in cht_list):
        language = "cht"
    elif any(indicator in subtitle_file_name.lower() for indicator in jp_sc_list):
        language = "jp_sc"
    elif any(indicator in subtitle_file_name.lower() for indicator in jp_tc_list):
        language = "jp_tc"
    else:
        language = ""

    sub_author = re.search(r'(^\[)(\w|\d|\-|\_|\&|\.|\!)+(\]+?)', subtitle_file_name)
    if sub_author is not None:
        sub_author = sub_author.group(0)
    else:
        sub_author = ""

    return {
        "language": language,
        "sub_author": sub_author.replace("[", "").replace("]", "")
    }


if __name__ == '__main__':
    try:
        if DELETE_ORIGINAL_MKV and RENAME_ORIGINAL_MKV:
            print("Rename MKV instead")
            DELETE_ORIGINAL_MKV = False
        if DELETE_ORIGINAL_MKA and RENAME_ORIGINAL_MKA:
            print("Rename MKA instead")
            DELETE_ORIGINAL_MKA = False
        if DELETE_CHS_SUB and RENAME_CHS_SUB:
            print("Rename CHS instead")
            DELETE_ORIGINAL_MKA = False
        if DELETE_CHT_SUB and RENAME_CHT_SUB:
            print("Rename CHT instead")
            DELETE_ORIGINAL_MKA = False
        delete_list = []
        rename_list = []

        # A useful global variable
        folder_list = os.listdir()

        # Prepare fonts
        font_list = []
        if os.path.exists("Fonts"):
            font_list = os.listdir("Fonts")
            print("Loading fonts: " + str(font_list))
        else:
            for file_name in folder_list:
                if "font" in file_name.lower() and ".zip" in file_name:
                    print("Find font package file: " + file_name)
                    if not os.path.exists("Fonts"):
                        os.makedirs("Fonts")
                        print("Fonts sub-directory created")
                    font_list = unzip(file_name, "GBK")
                    print("Unzipped to /Fonts: " + str(font_list))
                    print("=" * 20)
                elif "Font" in file_name and ".7z" in file_name:
                    print("Find font package file: " + file_name)
                    if not os.path.exists("Fonts"):
                        os.makedirs("Fonts")
                        print("Fonts sub-directory created")
                    with py7zr.SevenZipFile(file_name, mode='r') as z:
                        z.extractall("Fonts")
                        font_list = z.getnames()
                        print("Unzipped to /Fonts: " + str(font_list))
                else:
                    pass

        # Generate two useful list to reduce chance traversing folder_list in main task loop
        folder_mkv_list = [file for file in folder_list if file.endswith(".mkv")]
        folder_other_file_list = [file for file in folder_list if not file.endswith(".mkv")]

        # input("waiting...")
        # Main tasks
        for MKV_file_name in folder_mkv_list:
            # Initial variables
            skip_this_task = True

            if SUFFIX_NAME not in MKV_file_name:
                # Generate the task with MKV file
                print("Task start: " + MKV_file_name)
                MKV_name_no_extension = MKV_file_name.replace(".mkv", "")
                this_task = MKVFile(MKV_file_name)

                if DELETE_ORIGINAL_MKV:
                    delete_list.append(MKV_file_name)
                if RENAME_ORIGINAL_MKV:
                    rename_list.append(MKV_file_name)

                for item in folder_other_file_list:
                    # Match resources based on file name
                    if MKV_name_no_extension in item:
                        if item.endswith(".ass"):
                            # Add Subtitle track
                            this_sub_info = subtitle_info_checker(item)
                            if this_sub_info["language"] != "":
                                this_sub_track = MKVTrack(item,
                                                          track_name=this_sub_info["language"] + " " + this_sub_info[
                                                              "sub_author"],
                                                          default_track=True, language="chi")
                                skip_this_task = False
                                this_task.add_track(this_sub_track)
                                print("Find " + this_sub_info["language"] + " subtitle: " + item)
                                if DELETE_CHS_SUB:
                                    delete_list.append(item)
                                if RENAME_CHS_SUB:
                                    rename_list.append(item)
                        if item.endswith(".mka"):
                            # Add MKA track
                            skip_this_task = False
                            this_task.add_track(item)
                            print("Find associated audio: " + item)
                            if DELETE_ORIGINAL_MKA:
                                delete_list.append(item)
                            if RENAME_ORIGINAL_MKA:
                                rename_list.append(item)
                    else:
                        # Expand the search range for other subgroups
                        # By matching up the episode number
                        this_ep_num = re.search(r'(\[)(\d{2})(\])', MKV_name_no_extension)
                        if this_ep_num is not None:
                            this_ep_num = this_ep_num.group(0)
                            sub_matched = False
                            if this_ep_num in item and item != MKV_file_name:
                                # this_ep_num = [01]
                                sub_matched = True
                            elif this_ep_num.replace("[", " ").replace("]", " ") in item and item != MKV_file_name:
                                # this_ep_num =  01 (one space before and after the number)
                                sub_matched = True

                            if sub_matched:
                                print("Using ep number " + this_ep_num + " to match subtitle file")
                                if item.endswith(".ass"):
                                    this_sub_info = subtitle_info_checker(item)
                                    print(this_sub_info)
                                    if this_sub_info["language"] != "":
                                        this_sub_track = MKVTrack(item,
                                                                  track_name=this_sub_info["language"] + " " +
                                                                             this_sub_info["sub_author"],
                                                                  default_track=True, language="chi")
                                        skip_this_task = False
                                        this_task.add_track(this_sub_track)
                                        print("Find " + this_sub_info["language"] + " subtitle: " + item)
                                        if DELETE_CHT_SUB:
                                            delete_list.append(item)
                                        if RENAME_CHT_SUB:
                                            rename_list.append(item)
                for font in font_list:
                    font = "Fonts/" + font
                    this_task.add_attachment(font)
                if not skip_this_task:
                    newMKV_name = MKV_name_no_extension + SUFFIX_NAME + ".mkv"
                    try:
                        print("")
                        this_task.mux(newMKV_name)
                    except ValueError:
                        # A mysterious error will not cause any problem
                        print("mkvmerge raised error: " + newMKV_name)
                    print("=" * 20)
                else:
                    print("No task for this MKV")

    except Exception as e:
        print(e)
        input("Error. Press Enter to exit...")

    try:
        # Clean up
        # 创建 Extra 目录
        ExtraFolderIsExists = os.path.exists("Extra")
        if not ExtraFolderIsExists:
            os.makedirs("Extra")
        try:
            shutil.rmtree("Fonts/")
            print("Remove Fonts Folder Successfully")
        except:
            print("Remove Fonts Folder Error")
        for file in delete_list:
            try:
                os.remove(file)
            except:
                print("Failed to delete " + file)
        for file in rename_list:
            # os.rename(file, file + ".bak")
            shutil.move(file, "Extra/" + file)

        input("Task finished. Press Enter to exit...")
    except Exception as e:
        print(e)
        input("Error at clean up stage. Press Enter to exit...")
