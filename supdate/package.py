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
