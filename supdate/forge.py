import json
import subprocess
import zipfile
from pathlib import Path

import requests

from .profile import Profile
from .vanilla import fetch_vanilla_profile


class ForgeUniversal:
    def __init__(self, vanilla_version: str, forge_version: str, folder: Path):
        self.vanilla_version = vanilla_version
        self.forge_version = forge_version
        self.folder = folder
        self.universal = folder / f"forge-{vanilla_version}-{forge_version}-universal.jar"

    def forge_profile(self) -> Profile:
        with zipfile.ZipFile(self.universal) as zf:
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


class ForgeInstaller(ForgeUniversal):
    def __init__(self, vanilla_version: str, forge_version: str, folder: Path):
        super().__init__(vanilla_version, forge_version, folder)
        self.installer = folder / f"forge-{vanilla_version}-{forge_version}-installer.jar"

    def download(self):
        res = requests.get(
            f"https://files.minecraftforge.net/maven/"
            f"net/minecraftforge/forge/"
            f"{self.vanilla_version}-{self.forge_version}/"
            f"{self.installer.name}",
            stream=True,
        )

        res.raise_for_status()
        with self.installer.open('wb') as fp:
            for chunk in res:
                fp.write(chunk)

    def install(self, *, auto_download=True):
        if auto_download and not self.installer.exists():
            self.download()
        
        subprocess.check_call(["java", "-jar", str(self.installer), "--installServer"], cwd=str(self.folder))
        assert self.universal.exists()
