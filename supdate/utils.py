from hashlib import sha1 as _sha1
from pathlib import Path


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
