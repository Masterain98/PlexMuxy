import zipfile
import zlib
from pathlib import Path


# https://gist.github.com/hideaki-t/c42a16189dd5f88a955d
def unzip(f: str, encoding: str) -> list:
    """
    Unzip a file and return the contents name in a list.
    :param f: original zip file name (path)
    :param encoding: encoding of the zip file
    :return: a list of the contents name
    """
    fonts_list = []
    with zipfile.ZipFile(f, 'r') as this_zip:
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
            try:
                if i[-1] == '/':
                    if not n.exists():
                        n.mkdir()
                else:
                    with n.open('wb') as w:
                        w.write(this_zip.read(i))
            except zlib.error:
                raise zlib.error("Unsupported compression, please manually zip the file...")
    print(fonts_list)
    return fonts_list
