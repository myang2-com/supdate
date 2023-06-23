import re
import shutil
import subprocess
import traceback
from dataclasses import dataclass
from distutils.version import LooseVersion
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import ParseResult, urljoin, urlparse

import requests

from .base import Provider
from ..profile import (
    InstallProfile,
    Library,
    LibraryArtifactDownload,
    LibraryDependency,
    LibraryDownloads,
    Profile,
)
from ..utils import is_file_in_jar, load_json_from_jar as in_jar
from ..utils import sha1_hexdigest
from ..vanilla import fetch_vanilla_profile
from ..versions import VersionRange

VERSION_JSON = "version.json"
INSTALL_JSON = "install_profile.json"

FORGE_MAVEN = "maven.minecraftforge.net"
FORGE_URI = "net/minecraftforge/forge"

# (standard name, full name)
# The former is used in Forge Maven URL path, and the latter is the name of a forge file.
@dataclass
class Form:
    standard: str
    full: str

class ForgeType(Enum):
    INSTALLER = "installer"
    UNIVERSAL = "universal"


DEFAULT_VERSION_FORM = Form("forge-{mc}-{forge}", full="forge-{mc}-{forge}-{type}")
SPECIFIC_VERSION_FORMS = {
    "[1.7, 1.7.10]": Form("forge-{mc}-{forge}-{mc}", full="forge-{mc}-{forge}-{mc}-{type}"),
    "[1.19, 1.19.4]": Form("{mc}-{forge}", full=DEFAULT_VERSION_FORM.full)
}
def get_forge_version_form(v: str) -> Form:
    for version_range, form in SPECIFIC_VERSION_FORMS.items():
        if v in VersionRange(version_range):
            return form

    return DEFAULT_VERSION_FORM


@dataclass
class ForgeBase:
    mc_version: str
    forge_version: str
    directory: Path

    type: ForgeType
    form: Form

    def get_fullname_with(self, _type: ForgeType):
        return self.form.full.replace(
            "{mc}", self.mc_version
        ).replace(
            "{forge}", self.forge_version
        ).replace(
            "{type}", _type.value
        )

    @property
    def vanilla_version(self):
        return self.mc_version

    @property
    def standard_name(self):
        return self.form.standard.replace(
            "{mc}", self.mc_version
        ).replace(
            "{forge}", self.forge_version
        )

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
        assert fp.inheritsFrom == self.mc_version, (fp.inheritsFrom, self.mc_version)

        profile = self.vanilla_profile
        profile.merge(fp)
        profile.inheritsFrom = None

        return profile

    @property
    def url(self):
        return f"https://{FORGE_MAVEN}/{FORGE_URI}/{self.standard_name}/{self.full_name}.jar"


@dataclass
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

        with self.jar.open("wb") as fp:
            for chunk in res:
                fp.write(chunk)

    def install(self, *, auto_download=True):
        if auto_download and not self.jar.exists():
            self.download_forge()

        subprocess.check_call(
            ["java", "-jar", str(self.jar.absolute()), "--installServer"],
            cwd=str(self.directory),
        )


def find_forge_version_in_path(path: Path) -> Optional[str]:
    version = None

    settings_cfg_path = path / "settings.cfg"
    if not version and settings_cfg_path.exists():
        settings = dict(read_settings_cfg(settings_cfg_path))
        version = f"{settings['MCVER']}-{settings['FORGEVER']}"

    if not version:
        found = set()
        for file in path.glob("forge-*.jar"):
            m = re.match("^forge-(.*?).jar$", file.name)
            if m:
                ver = m[1]
                if ver.endswith(("-installer", "-universal")):
                    ver = ver.rpartition("-")[0]

                found.add(ver)

        if len(found) == 1:
            version = found.pop()

    if version:
        assert version.count("-") == 1, version
        return version
    else:
        return None


@dataclass(repr=False)
class ForgeProvider(Provider):
    forge_path: Path
    libraries_path: Path
    libraries_url: str

    def __post_init__(self):
        self.libraries_url = self.libraries_url.rstrip("/")

    @classmethod
    def find_version(
        cls, instance_path: Path, version: Optional[str] = None
    ) -> tuple[str, str, str]:
        if version is None:
            version = find_forge_version_in_path(instance_path)
            if not version:
                raise Exception("can't find forge version")

        assert version.count("-") == 1
        vanilla_version, forge_version = version.split("-")
        return version, vanilla_version, forge_version

    @classmethod
    def get_profile_path(
        cls, instance_path: Path, vanilla_version: str, forge_version: str
    ) -> Path:
        return instance_path / f"forge-{vanilla_version}-{forge_version}.json"

    def auto_profile(
        self,
        instance_path: Path,
        version: Optional[str] = None,
        *,
        force_build: bool = False,
    ) -> tuple[Path, Profile]:
        version, vanilla_version, forge_version = self.find_version(
            instance_path, version
        )
        forge_profile_path = self.get_profile_path(
            instance_path, vanilla_version, forge_version
        )
        if not force_build and forge_profile_path.exists():
            try:
                forge_profile = self.get_profile(forge_profile_path)
                return forge_profile_path, forge_profile
            except Exception:
                traceback.print_exc()

        forge_profile = self.build_profile(vanilla_version, forge_version)
        forge_profile.write_to_path(forge_profile_path)
        return forge_profile_path, forge_profile

    def get_profile(self, forge_profile_path: Path) -> Profile:
        if not forge_profile_path.exists():
            raise Exception("can't find forge profile")

        forge_profile = Profile.read_from_path(forge_profile_path)
        libraries = ForgeLibrariesBuilder(forge_profile, self.forge_path)
        if not libraries.check_target(self.libraries_path):
            raise Exception("can't find libraries")

        return forge_profile

    def build_profile(self, vanilla_version: str, forge_version: str) -> Profile:
        form = get_forge_version_form(vanilla_version)
        forge_installer = ForgeInstaller(
            mc_version=vanilla_version,
            forge_version=forge_version,
            directory=self.forge_path,
            form=form,
        )
        forge_installer.install()

        forge_profile = forge_installer.full_profile
        install_profile = forge_installer.install_profile

        libraries = ForgeLibrariesBuilder(
            forge_profile, self.forge_path, forge_installer
        )
        libraries.update_from_install_profile(install_profile, self.libraries_url)
        libraries.build(self.libraries_url, self.libraries_path, copy=True)

        return forge_profile


def is_forge_universal(library: Library):
    return library.group == "net.minecraftforge" and library.artifact == "forge"


class ForgeLibrariesBuilder:
    def __init__(self, profile: Profile, folder: Path, forge_base: ForgeBase = None):
        self.profile = profile
        self.folder = folder
        self.forge_base = forge_base

    def check_source(self):
        for library in self.profile.libraries:
            if library.clientreq or library.serverreq:
                lib = self.folder / "libraries" / library.path
                assert lib.exists(), lib
            elif library.downloads:
                assert library.downloads.artifact or library.downloads.classifiers
            else:
                assert is_forge_universal(library), library

    def check_all_forge_jars(self, path: Path):
        universal_jar = path.with_stem(f"{path.stem}-universal")
        server_jar = path.with_stem(f"{path.stem}-server")
        client_jar = path.with_stem(f"{path.stem}-client")

        if universal_jar.exists() and server_jar.exists():
            if not client_jar.exists():
                raise Exception(f"client jar file is missing: {client_jar}")

            return True
        else:
            return False

    def update_from_install_profile(
        self, install_profile: Optional[InstallProfile], url: str
    ):
        if install_profile is None or install_profile.data is None:
            return
        elif "MCP_VERSION" not in install_profile.data:
            return

        # get vanilla/mcp version
        mc_vanilla_version = self.forge_base.vanilla_version
        mcp_client_version = install_profile.data["MCP_VERSION"]["client"].strip("'\"")
        version = f"{mc_vanilla_version}-{mcp_client_version}"

        libraries_folder = self.folder / "libraries"

        # check corresponding version of (extra, silm, srg) jar file exists
        # check forge 1.13+ libraries/net/minecraft/client for more informations
        for tag in "extra", "slim", "srg":
            dependency = LibraryDependency(
                group="net.minecraft",
                artifact="client",
                version=version,
                tag=tag,
            )

            path = dependency.as_path()
            file = libraries_folder / path

            library = Library(
                name=":".join(filter(None, dependency)),
                clientreq=True,
                downloads=self.build_artifact_download(file, path, url),
                _dependency=dependency,
            )

            if not file.exists():
                raise Exception(f"file is missing: {file}")

            self.profile.libraries.append(library)

    def build(self, url: str, target_libraries_folder: Path, *, copy: bool):
        self.check_source()

        up: ParseResult = urlparse(url)
        if up.scheme not in ("http", "https"):
            raise Exception(f"protocol {up.scheme!r} is not supported")

        libraries_folder = self.folder / "libraries"
        for pos, library in enumerate(self.profile.libraries[:]):
            file = libraries_folder / library.path
            path = file.relative_to(libraries_folder)

            if library.clientreq or library.serverreq:
                if library.version < LooseVersion("1.13"):
                    assert not library.downloads
            elif is_forge_universal(library):
                if self.check_all_forge_jars(file):
                    for tag in "universal", "client":
                        sfile = file.with_stem(f"{file.stem}-{tag}")
                        spath = path.with_stem(f"{file.stem}-{tag}")
                        assert sfile.exists(), sfile

                        download = self.build_artifact_download(sfile, spath, url)

                        if copy:
                            self.copy_library_file(
                                sfile, spath, target_libraries_folder
                            )

                        new_library = Library(
                            name=f"{library.name}-{tag}",
                            downloads=LibraryDownloads(artifact=download),
                            _dependency=library._dependency.replace(tag=tag),
                        )
                        self.profile.libraries.insert(pos + 1, new_library)
                else:
                    file = self.forge_base.universal
            else:
                continue

            assert file.exists(), file

            download = self.build_artifact_download(file, path, url)
            library.downloads = LibraryDownloads(artifact=download)

            if copy:
                self.copy_library_file(file, path, target_libraries_folder)

    def build_artifact_download(self, file: Path, path: Path, url):
        return LibraryArtifactDownload(
            size=file.stat().st_size,
            sha1=sha1_hexdigest(file),
            path=path.as_posix(),
            url=urljoin(url, path.as_posix()),
        )

    def copy_library_file(self, file: Path, path: Path, target_libraries_folder: Path):
        target = target_libraries_folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(str(file.absolute()), str(target.absolute()))

    def check_target(self, target_libraries_folder: Path) -> bool:
        success = True

        for library in self.profile.libraries:
            if library.clientreq or library.serverreq:
                lib = target_libraries_folder / library.path
                if not lib.exists():
                    success = False
                    print(lib)

        return success


def read_settings_cfg(settings_cfg_path: Path):
    with settings_cfg_path.open() as fp:
        for line in fp:
            line = line.strip()
            if line.startswith(";"):
                continue

            line = line.rstrip(";")
            key, sep, value = line.partition("=")
            if not sep:
                continue

            key = key.strip()
            value = value.strip()
            yield key, value
