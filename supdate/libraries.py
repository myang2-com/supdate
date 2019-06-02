import shutil
from pathlib import Path
from urllib.parse import urlparse, ParseResult, urljoin

from .profile import Profile, Library, LibraryArtifactDownload, LibraryDownloads
from .utils import sha1_hexdigest


def is_forge_universal(library: Library):
    return library.group == "net.minecraftforge" and library.artifact == "forge"


class LibrariesBuilder:
    def __init__(self, profile: Profile, folder: Path):
        self.profile = profile
        self.folder = folder

    def check_source(self):
        for library in self.profile.libraries:
            if library.clientreq or library.serverreq:
                lib = self.folder / "libraries" / library.path
                assert lib.exists(), lib
            elif library.downloads:
                assert library.downloads.artifact or library.downloads.classifiers
            else:
                assert is_forge_universal(library), library

    def build(self, url: str, target_libraries_folder: Path, *, copy: bool):
        self.check_source()

        up: ParseResult = urlparse(url)
        if up.scheme not in ("http", "https"):
            raise Exception(f"{up.scheme} is not supported protocol")

        libraries_folder = self.folder / "libraries"
        for library in self.profile.libraries:
            if library.clientreq or library.serverreq:
                lib = libraries_folder / library.path
                assert lib.exists(), lib

                lib_stat = lib.stat()

                download = LibraryArtifactDownload(
                    size=lib_stat.st_size,
                    sha1=sha1_hexdigest(lib),
                    path=lib.relative_to(libraries_folder).as_posix(),
                    url=urljoin(url, lib.relative_to(libraries_folder).as_posix())
                )

                if copy:
                    target = target_libraries_folder / lib.relative_to(libraries_folder)
                    target.parent.mkdir(parents=True, exist_ok=True)

                    if not target.exists():
                        shutil.copyfile(str(lib.absolute()), str(target.absolute()))

                assert not library.downloads
                library.downloads = LibraryDownloads(artifact=download)

    def check_target(self, target_libraries_folder: Path) -> bool:
        success = True

        for library in self.profile.libraries:
            if library.clientreq or library.serverreq:
                lib = target_libraries_folder / library.path
                if not lib.exists():
                    success = False
                    print(lib)

        return success
