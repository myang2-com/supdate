import json
import subprocess
from typing import Optional
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .profile import Profile, InstallProfile
from .vanilla import fetch_vanilla_profile


class FileNotFoundInZipError(FileNotFoundError):
    pass


@dataclass
class ForgeUniversal:
    vanilla_version: str
    forge_version: str
    folder: Path
    universal: Path = None

    def find_universal_file(self):
        standard_filename = self.folder / \
            self.build_standard_filename(
                self.vanilla_version, self.forge_version)
        if standard_filename.exists():
            return standard_filename

        universal_file = self.folder / \
            self.build_universal_filename(
                self.vanilla_version, self.forge_version)
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

    @classmethod
    def load_version_from_jar(cls, path: Path) -> Profile:
        data = cls.load_json_from_jar(path, "version.json")
        return Profile.from_json(data)

    @staticmethod
    def load_json_from_jar(path: Path, name: str) -> dict:
        with zipfile.ZipFile(path) as zf:
            try:
                fp = zf.open(name)
            except KeyError:
                raise FileNotFoundInZipError(name)

            with fp:
                content = fp.read().decode('utf-8')
                return json.loads(content)

    def vanilla_profile(self) -> Profile:
        return fetch_vanilla_profile(self.vanilla_version)

    def full_profile(self) -> Profile:
        forge_profile = self.forge_profile()
        assert forge_profile.inheritsFrom == self.vanilla_version, (
            forge_profile.inheritsFrom, self.vanilla_version)

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

    def forge_profile(self) -> Profile:
        try:
            return self.load_version_from_jar(self.installer)
        except FileNotFoundInZipError as e:
            return self.load_version_from_jar(self.universal)

    def install_profile(self) -> Optional[InstallProfile]:
        return self.load_install_profile_from_jar(self.installer)

    def load_install_profile_from_jar(self, path: Path) -> Optional[InstallProfile]:
        try:
            data = self.load_json_from_jar(path, "install_profile.json")
            return InstallProfile.from_json(data)
        except FileNotFoundInZipError:
            return None

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
