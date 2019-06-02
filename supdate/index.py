from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from .package import Package
from .typed import Namespace
from .utils import sha1_hexdigest


@dataclass
class IndexPackage(Namespace):
    name: str
    version: str
    time: str
    url: str
    path: str
    sha1: str
    size: int

    @classmethod
    def from_package(cls, package: Package, modpack_path: Path, package_url: str):
        assert modpack_path.name == "modpack.json", modpack_path
        st = modpack_path.stat()

        return cls(
            name=package.name,
            version=package.version,
            time=package.time,
            url=package_url,
            path="modpack.json",
            sha1=sha1_hexdigest(modpack_path),
            size=st.st_size,
        )


@dataclass
class Launcher(Namespace):
    version: str
    url: str


@dataclass
class IndexPackageManifest(Namespace):
    version: str
    time: str
    launcher: Launcher
    packages: Dict[str, IndexPackage] = field(default_factory=dict)
