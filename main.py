import os
import shutil
import subprocess
import zipfile
from pymkv import MKVFile, MKVTrack
from pathlib import Path
import py7zr
import re

# Global Variable
DELETE_FONTS = False
DELETE_ORIGINAL_MKV = False
DELETE_ORIGINAL_MKA = False
DELETE_SUB = False
SUFFIX_NAME = "_Plex"


# https://gist.github.com/hideaki-t/c42a16189dd5f88a955d
def unzip(f: str, encoding: str) -> list:
    """
    Unzip a file and return the contents name in a list.
    :param f: original zip file name (path)
    :param encoding: encoding of the zip file
    :return: a list of the contents name
    """
    fonts_list = []
    with zipfile.ZipFile(f) as this_zip:
        for i in this_zip.namelist():
            try:
                # GBK
                fonts_list.append("Fonts/" + i.encode('cp437').decode(encoding))
                n = Path("Fonts/" + i.encode('cp437').decode(encoding))
            except UnicodeDecodeError:
                # UTF-8
                try:
                    fonts_list.append("Fonts/" + i.encode('utf-8').decode(encoding))
                    n = Path("Fonts/" + i.encode('utf-8').decode(encoding))
                except UnicodeDecodeError:
                    # Usually JPN
                    raise UnicodeDecodeError("Unsupported encoding, please manually zip the file...")
            if i[-1] == '/':
                if not n.exists():
                    n.mkdir()
            else:
                with n.open('wb') as w:
                    w.write(z.read(i))
    return fonts_list


def subtitle_info_checker(subtitle_file_name: str) -> dict:
    """
    Check the subtitle file name and analyze language and group information
    :param subtitle_file_name: subtitle file name (path)
    :return: a dictionary of language and group information, empty string if not found
    """
    # zh-CN
    CHS_LIST = [".chs", ".sc", "[chs]", "[sc]", ".gb", "[gb]"]
    # zh-TW or zh-HK
    CHT_LIST = [".cht", ".tc", "[cht]", "[tc]", "big5", "[big5]"]
    # Jpn and zh-CN
    JP_SC_LIST = [".jpsc", "[jpsc]", "jp_sc", "[jp_sc]", "chs&jap", "简日"]
    # Jpn and zh-TW/zh-HK
    JP_TC_LIST = [".jptc", "[jptc]", "jp_tc", "[jp_tc]", "cht&jap", "繁日"]
    # Jpn
    JP_LIST = [".jp", ".jpn", ".jap", "[jp]", "[jpn]", "[jap]"]

    if any(indicator in subtitle_file_name.lower() for indicator in JP_SC_LIST):
        language = "jp_sc"
    elif any(indicator in subtitle_file_name.lower() for indicator in JP_TC_LIST):
        language = "jp_tc"
    elif any(indicator in subtitle_file_name.lower() for indicator in CHS_LIST):
        language = "chs"
    elif any(indicator in subtitle_file_name.lower() for indicator in CHT_LIST):
        language = "cht"
    elif any(indicator in subtitle_file_name.lower() for indicator in JP_LIST):
        language = "jpn"
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


def is_font_file(f: str) -> bool:
    """
    Check the file extension if is a font
    :param f: file name (path)
    :return: true if is a font file, false if not
    """
    ALLOWED_FONT_EXTENSIONS = [".ttf", ".otf", ".ttc"]
    if any(f.lower().endswith(ext) for ext in ALLOWED_FONT_EXTENSIONS):
        return True
    else:
        return False


if __name__ == '__main__':
    delete_list = []
    move_list = []

    if SUFFIX_NAME == "":
        SUFFIX_NAME = "_Plex"

    try:
        # A useful global variable
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
                    unfiltered_font_list = unzip(file_name, "GBK")
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
                this_task = MKVFile(MKV_file_name)

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
                                track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                                if this_sub_info["language"] == "jpn":
                                    this_sub_track = MKVTrack(item, track_name=track_name,
                                                              default_track=True, language="jpn")
                                else:
                                    this_sub_track = MKVTrack(item, track_name=track_name,
                                                              default_track=True, language="chi")
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
                                        track_name = this_sub_info["language"] + " " + this_sub_info["sub_author"]
                                        if this_sub_info["language"] == "jpn":
                                            this_sub_track = MKVTrack(item, track_name=track_name,
                                                                      default_track=True, language="jpn")
                                        else:
                                            this_sub_track = MKVTrack(item, track_name=track_name,
                                                                      default_track=True, language="chi")
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
            # input("waiting...")
    except Exception as e:
        print("Error: " + str(e))

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
