from pathlib import Path
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from pydantic import BaseModel, parse_obj_as

from supdate.profile import Library, LibraryArtifactDownload, LibraryDownloads, Profile
from supdate.providers.base import Provider
from supdate.vanilla import fetch_vanilla_profile


class FabricProvider(Provider):
    @classmethod
    def get_profile_path(
        cls, instance_path: Path, vanilla_version: str, fabric_version: str
    ) -> Path:
        return instance_path / f"fabric-{vanilla_version}-{fabric_version}.json"

    @classmethod
    def find_version(cls, vanilla_version: str) -> tuple[str, str]:
        if "-" in vanilla_version:
            return tuple(vanilla_version.split("-"))  # type: ignore

        fabric_meta = FabricMetaClient()

        compatible_loader_versions = fabric_meta.list_compatible_loaders(
            game_version=vanilla_version
        )
        for compatible_loader_version in compatible_loader_versions:
            if (
                compatible_loader_version.intermediary.stable
                and compatible_loader_version.loader.stable
            ):
                break
        else:
            raise ValueError("No stable compatible loader version found")

        return (
            compatible_loader_version.intermediary.version,
            compatible_loader_version.loader.version,
        )

    def auto_profile(
        self,
        instance_path: Path,
        version: Optional[str] = None,
        *,
        force_build: bool = False,
    ) -> tuple[Path, Profile]:
        if not version:
            raise Exception("can't find vanilla version")

        vanilla_version, fabric_version = self.find_version(version)

        forge_profile_path = self.get_profile_path(
            instance_path, vanilla_version, fabric_version
        )
        if not force_build and forge_profile_path.exists():
            try:
                fabric_profile = self.get_profile(forge_profile_path)
                return forge_profile_path, fabric_profile
            except FileNotFoundError:
                pass

        fabric_profile = self.build_profile(vanilla_version, fabric_version)
        fabric_profile.write_to_path(forge_profile_path)
        return forge_profile_path, fabric_profile

    def get_profile(self, profile_path: Path) -> Profile:
        if profile_path.exists():
            return Profile.read_from_path(profile_path)

        raise FileNotFoundError(profile_path)

    def build_profile(self, vanilla_version: str, fabric_version: str) -> Profile:
        fabric_meta = FabricMetaClient()

        fabric_profile_json = fabric_meta.get_loader_profile_json(
            game_version=vanilla_version,
            loader_version=fabric_version,
        )

        fabric_profile = Profile.from_json(fabric_profile_json)

        FabricLibrariesBuilder(fabric_profile).build()

        assert fabric_profile.inheritsFrom == vanilla_version, (
            fabric_profile.inheritsFrom,
            vanilla_version,
        )

        vanilla_profile = fetch_vanilla_profile(vanilla_version)

        profile = vanilla_profile
        profile.merge(fabric_profile)
        profile.inheritsFrom = None

        return profile


class FabricGame(BaseModel):
    version: str
    stable: bool


class FabricIntermediary(BaseModel):
    maven: str
    version: str
    stable: bool


class FabricYarn(BaseModel):
    gameVersion: str
    separator: str
    build: int
    maven: str
    version: str
    stable: bool


class FabricLoader(BaseModel):
    separator: str
    build: int
    maven: str
    version: str
    stable: bool


class FabricCompatibleLoader(BaseModel):
    loader: FabricLoader
    intermediary: FabricIntermediary
    launcherMeta: dict


class FabricMetaClient:
    URL = "https://meta.fabricmc.net"

    def __init__(self):
        self.session = requests.session()

    def get(self, path):
        return self.session.get(urljoin(self.URL, path)).json()

    def list_versions(self) -> list[dict]:
        data = self.get("/v2/versions")
        return parse_obj_as(list[dict], data)

    def list_game_versions(self) -> list[FabricGame]:
        data = self.get("/v2/versions/game")
        return parse_obj_as(list[FabricGame], data)

    def list_game_versions_for_yarn(self) -> list[FabricGame]:
        data = self.get("/v2/versions/game/yarn")
        return parse_obj_as(list[FabricGame], data)

    def list_game_versions_for_intermediary(self) -> list[FabricGame]:
        data = self.get("/v2/versions/game/intermediary")
        return parse_obj_as(list[FabricGame], data)

    def list_intermediary_versions(
        self, *, game_version: Optional[str] = None
    ) -> list[FabricIntermediary]:
        if game_version is not None:
            data = self.get(f"/v2/versions/intermediary/{game_version}")
        else:
            data = self.get("/v2/versions/intermediary")

        return parse_obj_as(list[FabricIntermediary], data)

    def get_intermediary_version(self, *, game_version: str) -> FabricIntermediary:
        intermediary_list = self.list_intermediary_versions(game_version)
        if len(intermediary_list) != 1:
            raise ValueError(
                f"Expected only one intermediary version for {game_version}, got {len(intermediary_list)}"
            )

        return intermediary_list[0]

    def list_yarn_versions(
        self, *, game_version: Optional[str] = None
    ) -> list[FabricYarn]:
        if game_version is not None:
            data = self.get(f"/v2/versions/yarn/{game_version}")
        else:
            data = self.get("/v2/versions/yarn")

        return parse_obj_as(list[FabricYarn], data)

    def list_loader_versions(self) -> list[FabricLoader]:
        data = self.get("/v2/versions/loader")
        return parse_obj_as(list[FabricLoader], data)

    def list_compatible_loaders(
        self, *, game_version: Optional[str] = None
    ) -> list[FabricCompatibleLoader]:
        data = self.get(f"/v2/versions/loader/{game_version}")
        return parse_obj_as(list[FabricCompatibleLoader], data)

    def get_loader_version(
        self, *, game_version: str, loader_version: str
    ) -> FabricLoader:
        data = self.get(f"/v2/versions/loader/{game_version}/{loader_version}")

        return parse_obj_as(FabricLoader, data)

    def get_loader_profile_json(self, *, game_version: str, loader_version: str):
        data = self.get(
            f"/v2/versions/loader/{game_version}/{loader_version}/profile/json"
        )

        return parse_obj_as(dict, data)

    def get_loader_profile_zip(
        self, *, game_version: str, loader_version: str
    ) -> requests.Response:
        response = self.session.get(
            urljoin(
                self.URL,
                f"/v2/versions/loader/{game_version}/{loader_version}/profile/zip",
            )
        )

        return response

    def get_loader_server_json(self, *, game_version: str, loader_version: str):
        data = self.get(
            f"/v2/versions/loader/{game_version}/{loader_version}/server/json"
        )

        return parse_obj_as(dict, data)


class FabricLibrariesBuilder:
    def __init__(self, profile: Profile):
        self.profile = profile

    def build(self):
        for pos, library in enumerate(self.profile.libraries[:]):  # type: int, Library
            path = library.path.as_posix()

            file_size = int(
                requests.head(urljoin(library.url, library.path.as_posix())).headers[
                    "Content-Length"
                ]
            )

            file_sha1 = requests.get(
                urljoin(library.url, f"{library.path.as_posix()}.sha1")
            ).content.decode(errors="replace")
            if len(file_sha1) != 40 or not file_sha1.isalnum():
                raise Exception(f"Invalid SHA1 {file_sha1[:80]!r}")

            library.downloads = LibraryDownloads(
                artifact=LibraryArtifactDownload(
                    size=file_size,
                    sha1=file_sha1,
                    path=path,
                    url=urljoin(library.url, path),
                )
            )
