import json
from distutils.version import LooseVersion
from hashlib import sha1 as _sha1
from pathlib import Path
from typing import List, Union
from zipfile import ZipFile


class VersionRange:
    def __init__(self, vrange: str):
        versions: List[str] = list(map(lambda v: v.strip(), vrange.split(",")))
        if len(versions) != 2:
            raise ValueError(f"{vrange} is not a valid version range.")
        elif all(
            (
                versions[0][0] == "[" or versions[0][0] == "(",
                versions[1][-1] == "]" or versions[1][-1] == ")",
            )
        ):
            if len(versions[0][1:]) == 0 or versions[0] == "*":
                self.__left = None
            else:
                self.__left = LooseVersion(versions[0][1:])

            if len(versions[1][:-1]) == 0 or versions[1] == "*":
                self.__right = None
            else:
                self.__right = LooseVersion(versions[1][:-1])

            self.__lopen = versions[0][0] == "("
            self.__ropen = versions[1][-1] == ")"
            self.__empty = all(
                (
                    self.__left is None,
                    self.__right is None,
                    (self.__lopen or self.__ropen),
                )
            )
        else:
            raise ValueError(
                "The range must be given by the form of mathematical intervals."
            )

    @property
    def left(self):
        return self.__left

    @property
    def right(self):
        return self.__right

    @property
    def lopen(self):
        return self.__lopen

    @property
    def ropen(self):
        return self.__ropen

    @property
    def lclosed(self):
        return not self.__lopen

    @property
    def rclosed(self):
        return not self.__ropen

    def __contains__(self, item: Union[LooseVersion, str]):
        if self.__empty:
            return False
        if self.left is not None:
            if (item < self.left) or (self.lopen and item == self.left):
                return False
        if self.right is not None:
            if (item > self.right) or (self.ropen and item == self.right):
                return False

        return True


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
