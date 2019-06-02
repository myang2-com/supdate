from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from .profile import Profile
from .typed import Namespace
from .utils import sha1_hexdigest, is_same_file


@dataclass
class PackageFile(Namespace):
    size: int
    sha1: str
    path: str
    url: str


@dataclass
class PackageConfig:
    includes: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)


@dataclass(repr=False)
class Package(Profile):
    name: Optional[str] = None
    version: Optional[str] = None
    files: List[PackageFile] = field(default_factory=list)

    @classmethod
    def from_profile(cls, profile: Profile) -> Package:
        return cls.from_json(profile.to_json())

    def to_json(self) -> dict:
        prev_obj = super().to_json()
        obj = {
            "id": prev_obj.pop("id"),
            "name": prev_obj.pop("name"),
            "version": prev_obj.pop("version"),
        }

        files = prev_obj.pop("files")
        obj.update(prev_obj)

        obj["files"] = files
        return obj


class PackageBuilder:
    def __init__(self, package: Package, instance_folder: Path, package_folder: Path, package_url: str):
        self.package = package
        self.instance_folder = instance_folder
        self.package_folder = package_folder
        self.package_url = package_url
        self.files: Dict[Path, Any] = {}

    def scan(self, pattern: str, folder: Optional[Path] = None):
        if folder is None:
            folder = self.instance_folder

        for file in folder.glob(pattern):
            if file.is_file():
                yield file, file.relative_to(folder)

    def include(self, pattern: str, folder: Optional[Path] = None):
        for file, path in self.scan(pattern, folder=folder):
            self.files[path] = file

    def exclude(self, pattern: str, folder: Optional[Path] = None):
        for _, path in self.scan(pattern, folder=folder):
            self.files.pop(path, None)

    def build(self):
        # TODO: delete mismatch
        for path, file in self.files.items():
            target_file = self.package_folder / path
            target_file.parent.mkdir(parents=True, exist_ok=True)

            if is_same_file(file, target_file):
                shutil.copyfile(str(file), str(target_file))

            file_stat = file.stat()
            self.package.files.append(PackageFile(
                size=file_stat.st_size,
                sha1=sha1_hexdigest(file),
                path=path.as_posix(),
                url=urljoin(self.package_url, path.as_posix())
            ))
