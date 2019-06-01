from dataclasses import dataclass
from typing import Any, List

import requests

from .profile import Profile
from .typed import Namespace


@dataclass(repr=False)
class VanillaVersion(Namespace):
    id: str
    type: str
    url: str
    time: str
    releaseTime: str

    def fetch(self):
        return Profile.from_json(requests.get(self.url).json())


@dataclass(repr=False)
class VanillaVersionManifest(Namespace):
    URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

    latest: Any
    versions: List[VanillaVersion]

    def __post_init__(self):
        self.cache = {version.id: version for version in self.versions}

    def __getitem__(self, item) -> VanillaVersion:
        return self.cache[item]

    def __contains__(self, item):
        return item in self.cache

    def __iter__(self):
        return iter(self.versions)

    @classmethod
    def fetch(cls):
        return cls.from_json(requests.get(cls.URL).json())


def fetch_vanilla_profile(vanilla_version: str) -> Profile:
    vanilla_manifest = VanillaVersionManifest.fetch()
    return vanilla_manifest[vanilla_version].fetch()
