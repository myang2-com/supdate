import json
from hashlib import sha1 as _sha1
from pathlib import Path
from zipfile import ZipFile


def load_json_from_jar(jar: Path, filename: str) -> dict:
    with ZipFile(jar) as zf:
        try:
            fp = zf.open(filename)
        except KeyError:
            raise FileNotFoundError(f"{filename} does not exist in {jar.absolute()}!")

        with fp:
            content = fp.read().decode("utf-8")
            return json.loads(content)


def is_file_in_jar(jar: Path, filename: str) -> bool:
    with ZipFile(jar) as zf:
        return filename in zf.namelist()


def sha1_hexdigest(file: Path):
    if not file.exists():
        raise FileNotFoundError(str(file))
    elif not file.is_file():
        raise FileExistsError((str(file)), "is not a file.")

    return _sha1(file.read_bytes()).hexdigest()


def is_same_file(a: Path, b: Path):
    if not a.exists() or not b.exists():
        return False

    return sha1_hexdigest(a) == sha1_hexdigest(b)
