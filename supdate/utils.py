from hashlib import sha256 as _sha256
from pathlib import Path


def sha256_hexdigest(file: Path):
    return _sha256(file.read_bytes()).hexdigest()
