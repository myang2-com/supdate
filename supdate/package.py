from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable
from urllib.parse import urljoin

from .profile import Profile
from .typed import Namespace
from .utils import sha256_hexdigest


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
    files: List[PackageFile] = field(default_factory=list)

    @classmethod
    def from_profile(cls, profile: Profile) -> Package:
        return cls.from_json(profile.to_json())

    def scan(self, instance_folder):
        for file in instance_folder.rglob("**/*"):
            if not file.is_file():
                continue

            path: Path = file.relative_to(instance_folder)
            yield file, path

    def build(self, instance_folder: Path, url: str, target_folder: Path = None,
              func: Callable[[Path, Path], bool] = None):
        for file, path in self.scan(instance_folder):
            if func:
                result = func(file, path)
                if result is not None and not result:
                    continue

            if target_folder is not None:
                target_path: Path = target_folder / path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(file), str(target_path))

            file_stat = file.stat()
            self.files.append(PackageFile(
                size=file_stat.st_size,
                sha1=sha256_hexdigest(file),
                path=path.as_posix(),
                url=urljoin(url, file.relative_to(instance_folder).as_posix())
            ))
