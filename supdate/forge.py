import subprocess
import attr
import requests

from enum import Enum
from pathlib import Path
from typing import Optional
from distutils.version import LooseVersion
from collections import namedtuple

from .profile import Profile, InstallProfile
from .utils import is_file_in_jar, load_json_from_jar as in_jar, VersionRange
from .vanilla import fetch_vanilla_profile


VERSION_JSON = "version.json"
INSTALL_JSON = "install_profile.json"

FORGE_MAVEN = "maven.minecraftforge.net"
FORGE_URI = "net/minecraftforge/forge"

# (standard name, full name)
# The former is used in Forge Maven URL path, and the latter is the name of a forge file.
Form = namedtuple('Form', ['standard', 'full'])

DEFAULT_VERSION_FORM = Form("forge-{mc}-{forge}", full="forge-{mc}-{forge}-{type}")
SPECIFIC_VERSION_FORMS = {
    "[1.7, 1.7.10]": Form("forge-{mc}-{forge}-{mc}", full="forge-{mc}-{forge}-{mc}-{type}"),
    "[1.19, 1.19.4]": Form("{mc}-{forge}", full=DEFAULT_VERSION_FORM.full)
}
def get_version_form(v: str):
    for version_range, form in SPECIFIC_VERSION_FORMS.items():
        if v in VersionRange(version_range):
            return form

    return DEFAULT_VERSION_FORM

class ForgeType(Enum):
    INSTALLER = "installer"
    UNIVERSAL = "universal"


@attr.s(auto_attribs=True)
class ForgeBase:
    mc_version: str
    forge_version: str
    directory: Path
    type: ForgeType

    @property
    def form(self):
        return get_version_form(self.mc_version)

    @property
    def vanilla_version(self):
        return self.mc_version

    @property
    def standard_name(self):
        return self.form.standard.replace("{mc}", self.mc_version)       \
                                 .replace("{forge}", self.forge_version)

    def get_fullname_with(self, _type: ForgeType):
        return self.form.full.replace("{mc}", self.mc_version) \
                             .replace("{forge}", self.forge_version) \
                             .replace("{type}", _type.value)

    @property
    def full_name(self):
        return self.get_fullname_with(self.type)

    @property
    def jar(self) -> Path:
        return self.directory / f"{self.full_name}.jar"

    @property
    def universal(self):
        std_file = self.directory / f"{self.standard_name}.jar"
        if std_file.exists():
            return std_file

        univ_file = self.directory / f"{self.get_fullname_with(ForgeType.UNIVERSAL)}.jar"
        if univ_file.exists():
            return univ_file

        raise FileNotFoundError("Forge universal jar file has not been found.")

    def load_version(self):
        if is_file_in_jar(self.universal, VERSION_JSON):
            return Profile.from_json(in_jar(self.universal, VERSION_JSON))
        else:
            raise FileNotFoundError("Forge version profile json has not been found.")

    @property
    def forge_profile(self) -> Profile:
        return self.load_version()

    @property
    def vanilla_profile(self) -> Profile:
        return fetch_vanilla_profile(self.mc_version)

    @property
    def full_profile(self) -> Profile:
        fp = self.forge_profile
        assert fp.inheritsFrom == self.mc_version, (
            fp.inheritsFrom, self.mc_version
        )

        profile = self.vanilla_profile
        profile.merge(fp)
        profile.inheritsFrom = None

        return profile

    @property
    def url(self):
        return f"https://{FORGE_MAVEN}/{FORGE_URI}/{self.standard_name}/{self.full_name}.jar"


@attr.s(auto_attribs=True)
class ForgeInstaller(ForgeBase):
    type: ForgeType = ForgeType.INSTALLER

    @property
    def install_profile(self) -> Optional[InstallProfile]:
        try:
            return InstallProfile.from_json(in_jar(self.jar, INSTALL_JSON))
        except FileNotFoundError:
            return None

    def load_version(self):
        # From 1.13, Version.json is included in the installer jar.
        if self.mc_version < LooseVersion("1.13"):
            return super().load_version()
        elif is_file_in_jar(self.jar, VERSION_JSON):
            return Profile.from_json(in_jar(self.jar, VERSION_JSON))
        else:
            raise FileNotFoundError("Forge version profile json has not been found.")

    def download_forge(self):
        res = requests.get(self.url, stream=True)
        res.raise_for_status()

        with self.jar.open('wb') as fp:
            for chunk in res:
                fp.write(chunk)

    def install(self, *, auto_download=True):
        if auto_download and not self.jar.exists():
            self.download_forge()

        subprocess.check_call(["java", "-jar", str(self.jar.absolute()), "--installServer"], cwd=str(self.directory))
