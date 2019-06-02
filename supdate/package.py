from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
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
