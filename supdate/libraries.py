import shutil
from distutils.version import LooseVersion
from pathlib import Path
from typing import Optional
from urllib.parse import ParseResult, urljoin, urlparse

from .forge import ForgeBase
from .profile import (
    InstallProfile,
    Library,
    LibraryArtifactDownload,
    LibraryDependency,
    LibraryDownloads,
    Profile,
)
from .utils import sha1_hexdigest


def is_forge_universal(library: Library):
    return library.group == "net.minecraftforge" and library.artifact == "forge"


class LibrariesBuilder:
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
