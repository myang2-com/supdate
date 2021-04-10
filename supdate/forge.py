import json
from re import DEBUG
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .profile import Profile
from .vanilla import fetch_vanilla_profile


@dataclass
class ForgeUniversal:
    vanilla_version: str
    forge_version: str
    folder: Path
    universal: Path = None

    def find_universal_file(self):
        standard_filename = self.folder / self.build_standard_filename(self.vanilla_version, self.forge_version)
        if standard_filename.exists():
            return standard_filename

        universal_file = self.folder / self.build_universal_filename(self.vanilla_version, self.forge_version)
        if universal_file.exists():
            return universal_file

        raise Exception("forge-*.jar not exists")

    @staticmethod
    def build_standard_filename(vanilla_version: str, forge_version: str):
        return f"forge-{vanilla_version}-{forge_version}.jar"

    @staticmethod
    def build_universal_filename(vanilla_version: str, forge_version: str):
        return f"forge-{vanilla_version}-{forge_version}-universal.jar"

    def forge_profile(self) -> Profile:
        return self.load_version_from_jar(self.universal)

    @staticmethod
    def load_version_from_jar(path: Path) -> Profile:
        with zipfile.ZipFile(path) as zf:
            with zf.open("version.json") as fp:
                data = json.loads(fp.read().decode('utf-8'))
                return Profile.from_json(data)

    def vanilla_profile(self) -> Profile:
        return fetch_vanilla_profile(self.vanilla_version)

    def full_profile(self) -> Profile:
        forge_profile = self.forge_profile()
        assert forge_profile.inheritsFrom == self.vanilla_version

        vanilla_profile = self.vanilla_profile()
        vanilla_profile.merge(forge_profile)
        vanilla_profile.inheritsFrom = None

        profile = vanilla_profile
        return profile


@dataclass
class ForgeInstaller(ForgeUniversal):
    installer: Path = None

    def __post_init__(self):
        if self.installer is None:
            self.installer = self.folder / self.installer_name

    @property
    def installer_url(self):
        return (
            f"https://files.minecraftforge.net/maven/"
            f"net/minecraftforge/forge/"
            f"{self.vanilla_version}-{self.forge_version}/"
            f"{self.installer_name}"
        )

    @property
    def installer_name(self):
        return self.get_installer_name(self.vanilla_version, self.forge_version)

    @staticmethod
    def get_installer_name(vanilla_version: str, forge_version: str):
        return f"forge-{vanilla_version}-{forge_version}-installer.jar"

    def download(self):
        res = requests.get(self.installer_url, stream=True)
        res.raise_for_status()

        with self.installer.open('wb') as fp:
            for chunk in res:
                fp.write(chunk)

    def install(self, *, auto_download=True):
        if auto_download and not self.installer.exists():
            self.download()

        subprocess.check_call(["java", "-jar", str(self.installer.absolute()), "--installServer"], cwd=str(self.folder))
        self.universal = self.find_universal_file()

    def forge_profile(self) -> Profile:
        for file in self.installer, self.universal:
            try:
                return self.load_version_from_jar(file)
            except Exception:
                if file == self.installer:
                    raise
                else:
                    # ignore error
                    continue
