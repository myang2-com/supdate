from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import List, Optional, Any, NamedTuple

from .typed import Namespace


@dataclass(repr=False)
class InstallProfile(Namespace):
    version: str = None
    data: dict = None


@dataclass(repr=False)
class Profile(Namespace):
    # TODO: extend more
    id: str
    time: str
    releaseTime: str
    type: str
    mainClass: str
    # 1.7.10에선 Version profile에서 logging이 지원되지 않습니다.
    logging: dict = field(default_factory=dict)
    arguments: Optional[Any] = None
    minecraftArguments: str = None
    minimumLauncherVersion: float = None
    libraries: List[Library] = field(default_factory=list)
    jar: Optional[str] = None
    inheritsFrom: Optional[str] = None
    assetIndex: Optional[Any] = None
    downloads: Optional[Any] = None
    assets: Optional[str] = None

    def __post_init__(self):
        if self.arguments is not None:
            self.minecraftArguments = self.build_minecraft_arguments(self.arguments)

    def merge(self, other: Profile):
        for key, value in other.items():
            if key == "libraries":
                self[key] = list({library.name: library
                                  for library in chain(other.libraries, self.libraries)}.values())
            elif key == "arguments":
                self.arguments["game"].extend(value["game"])
            elif key == "minecraftArguments":
                # check for minecraftArguments is builded by arguments["game"]
                if self.arguments is not None:
                    self.minecraftArguments += " " + value
                else:
                    self.minecraftArguments = value
            elif isinstance(value, list):
                self[key].extend(value)
            elif isinstance(value, dict):
                self[key].update(value)
            else:
                self[key] = value

    def build_minecraft_arguments(self, arguments):
        return " ".join(arg for arg in arguments["game"] if isinstance(arg, str))


class LibraryDependency(NamedTuple):
    group: str
    artifact: str
    version: str
    tag: str = None

    def as_path(self) -> Path:
        return Path(
            posixpath.sep.join([
                self.group.replace('.', '/'),
                self.artifact,
                self.version,
                f"{'-'.join(filter(None, self[1:]))}.jar"
            ])
        )

    def replace(self, **kwargs) -> LibraryDependency:
        return self._replace(**kwargs)


@dataclass(repr=False)
class Library(Namespace):
    name: str
    url: Optional[str] = None
    checksums: List[str] = None
    serverreq: Optional[bool] = None
    clientreq: Optional[bool] = None
    downloads: Optional[LibraryDownloads] = None

    # private (do not serialize this field)
    _dependency: LibraryDependency = None

    def __post_init__(self):
        if self._dependency is None:
            assert self.name.count(":") in (2, 3), self.name
            if self.name.count(":") == 2:
                group, artifact, version = self.name.split(":")
            elif self.name.count(":") == 3:
                group, artifact, version, tag = self.name.split(":")

            self._dependency = LibraryDependency(group, artifact, version)

    @property
    def group(self) -> str:
        return self._dependency.group

    @property
    def artifact(self) -> str:
        return self._dependency.artifact

    @property
    def version(self) -> str:
        return self._dependency.version

    @property
    def path(self) -> str:
        return self._dependency.as_path()


@dataclass(repr=False)
class LibraryDownloads(Namespace):
    artifact: Optional[LibraryArtifactDownload] = None
    classifiers: Optional[Any] = None


@dataclass(repr=False)
class LibraryArtifactDownload(Namespace):
    size: Optional[int] = None
    sha1: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
