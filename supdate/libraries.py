import shutil
from pathlib import Path
from urllib.parse import urlparse, ParseResult, urljoin

from .forge import ForgeUniversal
from .profile import Profile, Library, LibraryArtifactDownload, LibraryDownloads
from .utils import sha1_hexdigest


def is_forge_universal(library: Library):
    return library.group == "net.minecraftforge" and library.artifact == "forge"


class LibrariesBuilder:
    def __init__(self, profile: Profile, folder: Path, forge_universal: ForgeUniversal = None):
        self.profile = profile
        self.folder = folder
        self.forge_universal = forge_universal

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
                file = libraries_folder / library.path
                path = file.relative_to(libraries_folder)
            elif is_forge_universal(library):
                # TODO: universal ref object?
                vanilla_version, forge_version = library.version.split('-')
                file = self.folder / ForgeUniversal.build_universal_filename(vanilla_version, forge_version)
                if not file.exists():
                    file = self.forge_universal.universal
                    if not file.exists():
                        raise Exception("I don't have any idea for find universal jar... T_T")

                path = Path(library.path)
            else:
                continue

            assert file.exists(), file

            lib_stat = file.stat()

            download = LibraryArtifactDownload(
                size=lib_stat.st_size,
                sha1=sha1_hexdigest(file),
                path=path.as_posix(),
                url=urljoin(url, path.as_posix())
            )

            if copy:
                target = target_libraries_folder / path
                target.parent.mkdir(parents=True, exist_ok=True)

                if not target.exists():
                    shutil.copyfile(str(file.absolute()), str(target.absolute()))

            if not is_forge_universal(library):
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
