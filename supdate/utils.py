from hashlib import sha1 as _sha1
from pathlib import Path

from zipfile import ZipFile
import json

def load_json_from_jar(jar: Path, filename: str) -> dict:
    with ZipFile(jar) as zf:
        try:
            fp = zf.open(filename)
        except KeyError:
            raise FileNotFoundError(f"{filename} does not exist in {jar.name}!")

        with fp:
            content = fp.read().decode('utf-8')
            return json.loads(content)

def sha1_hexdigest(file: Path):
    if not file.exists():
        raise FileNotFoundError(str(file))
    elif not file.is_file():
        raise FileExistsError((str(file)), "is not file")

    return _sha1(file.read_bytes()).hexdigest()


def is_same_file(a: Path, b: Path):
    if not a.exists() or not b.exists():
        return False

    return sha1_hexdigest(a) == sha1_hexdigest(b)
