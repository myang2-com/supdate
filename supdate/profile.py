from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from itertools import chain
from typing import List, Optional, Any, NamedTuple

from .typed import Namespace


@dataclass(repr=False)
class Profile(Namespace):
    # TODO: extend more
    id: str
    time: str
    releaseTime: str
    type: str
    minecraftArguments: str
    mainClass: str
    logging: dict
    libraries: List[Library] = field(default_factory=list)
    jar: Optional[str] = None
    inheritsFrom: Optional[str] = None
    assetIndex: Optional[Any] = None
    downloads: Optional[Any] = None
    assets: Optional[str] = None

    def merge(self, other: Profile):
        for key, value in other.items():
            if key == "libraries":
                self[key] = list({library.name: library
                                  for library in chain(self.libraries, other.libraries)}.values())
            elif isinstance(value, list):
                self[key].extend(value)
            elif isinstance(value, dict):
                self[key].update(value)
            else:
                self[key] = value


class LibraryDependency(NamedTuple):
    group: str
    artifact: str
    version: str


@dataclass(repr=False)
class Library(Namespace):
    name: str
    url: Optional[str] = None
    checksums: List[str] = None
    serverreq: Optional[bool] = None
    clientreq: Optional[bool] = None
    downloads: Optional[LibraryDownloads] = None
    _dependency: LibraryDependency = None

    def __post_init__(self):
        group, artifact, version = self.name.split(":")
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
        group, artifact, version = self._dependency
        return posixpath.sep.join([
            group.replace('.', '/'),
            artifact,
            version,
            f"{artifact}-{version}.jar",
        ])


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
