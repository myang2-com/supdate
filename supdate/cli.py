import compileall
import os
import re
import shutil
import tempfile
import zipapp
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple
from urllib.parse import urljoin
from packaging.version import parse as version_

import click
import requests_cache
from click import Group as Cli, Context

from .forge import ForgeInstaller
from .index import IndexPackageManifest, Launcher, IndexPackage
from .libraries import LibrariesBuilder
from .package import Package, PackageBuilder
from .profile import Profile
from .utils import sha1_hexdigest

DOMAIN = "myang2.com"

VERSION_FORMS = {
    "1.7.10": "forge-{mc}-{forge}-{mc}(-{type})",
    "default": "forge-{mc}-{forge}(-{type})"
}
def get_version_form(v: str):
    for key_version, form in VERSION_FORMS.items():
        if version_(v) == version_(key_version):
            return form

    return VERSION_FORMS["default"]


class ClickPath(click.Path):
    def coerce_path_result(self, rv):
        path = super().coerce_path_result(rv)
        return Path(path)


@dataclass(repr=False)
class SUpdate:
    forge_path: Path
    packages_path: Path
    instances_path: Path
    libraries_path: Path
    libraries_url: str
    packages_url: str
    current_datetime: str = None

    def __post_init__(self):
        self.libraries_url = self.libraries_url.rstrip('/')
        self.packages_url = self.packages_url.rstrip('/')
        self.current_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+0000")

    @property
    def index_path(self):
        return self.packages_path / "index.json"

    def prepare_forge(self, version: str, forge_path: Optional[Path] = None) -> Tuple[str, str, Path, Path]:
        assert version.count('-') == 1
        vanilla_version, sep, forge_version = version.partition('-')
        assert sep

        if forge_path is None:
            forge_path = self.forge_path / version
            forge_path.mkdir(parents=True, exist_ok=True)

        forge_profile_path = forge_path / f"forge-{version}.json"
        return vanilla_version, forge_version, forge_path, forge_profile_path

    def cmd_forge(
            self,
            version: str,
            *,
            forge_path: Optional[Path] = None
    ) -> Path:
        vanilla_version, forge_version, forge_path, forge_profile_path = self.prepare_forge(version, forge_path)

        form = get_version_form(vanilla_version)
        forge_installer = ForgeInstaller(vanilla_version, forge_version, forge_path, form)
        forge_installer.install()

        forge_profile = forge_installer.full_profile
        install_profile = forge_installer.install_profile

        libraries = LibrariesBuilder(forge_profile, forge_path, forge_installer)
        libraries.update_from_install_profile(install_profile, self.libraries_url)
        libraries.build(self.libraries_url, self.libraries_path, copy=True)

        forge_profile.write_to_path(forge_profile_path)
        return forge_profile_path

    def check_forge(
            self,
            version: str,
            *,
            forge_path: Optional[Path] = None,
    ) -> bool:
        _, _, forge_path, forge_profile_path = self.prepare_forge(version, forge_path)
        if not forge_path.exists():
            return False

        forge_profile = Profile.read_from_path(forge_profile_path)
        libraries = LibrariesBuilder(forge_profile, forge_path)
        return libraries.check_target(self.libraries_path)

    def cmd_package(
            self,
            name: str,
            forge_version: Optional[str] = None,
            update_forge: bool = None,
            *,
            from_cmd=False,
    ) -> Path:
        instance_path = self.instances_path / name
        package_path = self.packages_path / name
        modpack_path = package_path / "modpack.json"
        client_path = instance_path / "client"

        if not instance_path.exists():
            raise FileNotFoundError(str(instance_path))

        if not client_path.exists():
            client_path.mkdir(exist_ok=True, parents=True)

        if forge_version is None:
            forge_version = self.find_forge_version(instance_path)
            if not forge_version:
                raise Exception("can't find forge version")

        prev_manifest = self.get_latest_manifest()
        prev_package = Package.read_from_path(modpack_path) if modpack_path.exists() else None

        forge_profile_path = instance_path / f"forge-{forge_version}.json"
        if update_forge is not False and (
                update_forge or
                not forge_profile_path.exists() or
                not self.check_forge(forge_version, forge_path=instance_path)
        ):
            forge_profile_path = self.cmd_forge(forge_version, forge_path=instance_path)

        forge_profile = Profile.read_from_path(forge_profile_path)
        package = Package.from_profile(forge_profile)
        package.id = name
        package.name = prev_package.name if prev_package else name
        package.version = self.calc_version(prev_manifest.version)
        package.time = self.current_datetime

        assert not self.packages_url.endswith("/")
        package_url = f"{self.packages_url}/{name}/"

        package_builder = PackageBuilder(package, instance_path, package_path, package_url)
        package_builder.include("mods/**/*")
        package_builder.include("config/**/*")
        package_builder.include("scripts/**/*")

        # Builtin exclusions
        package_builder.exclude("config/Chikachi/**/*")

        # excludes all selected files from the server side
        exclusion_json = instance_path / "exclude.json"
        exclusion_key = "exclude"
        if not exclusion_json.exists():
            default_exclusion = {
                exclusion_key: [
                    "config/Chikachi/**/*",
                ]
            }
            exclusion_json.write_text(json.dumps(default_exclusion))

        try:
            with exclusion_json.open() as json_file:
                exclusion = json.load(json_file)

            if exclusion_key in exclusion and isinstance(exclusion[exclusion_key], list):
                for ignore in exclusion[exclusion_key]:
                    package_builder.exclude(ignore)

        except ValueError as err:
            raise Exception("Fatal error occurred from exclude.json") from err

        package_builder.build()

        client_builder = PackageBuilder(package, client_path, package_path, package_url)
        client_builder.include("**/*")
        client_builder.build()

        modpack_path.parent.mkdir(exist_ok=True)
        package.write_to_path(modpack_path)

        if not from_cmd:
            self.cmd_update()

        return modpack_path

    def cmd_update(self) -> Path:
        index_path = self.index_path

        prev_manifest = self.get_latest_manifest()
        next_version = self.calc_version(prev_manifest.version)
        next_datetime = self.current_datetime

        manifest = IndexPackageManifest(
            version=next_version,
            time=next_datetime,
            launcher=prev_manifest.launcher,
        )

        for package_path in self.packages_path.iterdir():
            if not package_path.is_dir():
                continue

            package_name = package_path.name
            modpack_path = package_path / "modpack.json"
            if not modpack_path.exists():
                print(package_name, "missing", "modpack.json")
                continue

            package = Package.read_from_path(modpack_path)

            prev_index_package = prev_manifest.packages.get(package.id) if prev_manifest else None
            if prev_index_package and prev_index_package.sha1 == sha1_hexdigest(modpack_path):
                index_package = prev_index_package
            else:
                package.version = next_version
                package.time = next_datetime
                package.write_to_path(modpack_path)

                index_package = IndexPackage.from_package(
                    package=package,
                    modpack_path=modpack_path,
                    package_url=urljoin(self.packages_url, f'{package_path.name}/'),
                )

            manifest.packages[package.id] = index_package

        manifest.write_to_path(index_path)
        return index_path

    def get_latest_manifest(self) -> IndexPackageManifest:
        if self.index_path.exists():
            return IndexPackageManifest.read_from_path(self.index_path)
        else:
            return IndexPackageManifest(
                version=self.calc_version(),
                time=self.current_datetime,
                launcher=Launcher(
                    version="0.0.0",
                    url="https://example.com/",
                )
            )

    @classmethod
    def find_forge_version(cls, path: Path) -> Optional[str]:
        version = None

        settings_cfg_path = path / "settings.cfg"
        if not version and settings_cfg_path.exists():
            settings = dict(cls.read_settings_cfg(settings_cfg_path))
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
            assert version.count('-') == 1, version
            return version
        else:
            return None

    @staticmethod
    def read_settings_cfg(settings_cfg_path: Path):
        with settings_cfg_path.open() as fp:
            for line in fp:
                line = line.strip()
                if line.startswith(';'):
                    continue

                line = line.rstrip(';')
                key, sep, value = line.partition("=")
                if not sep:
                    continue

                key = key.strip()
                value = value.strip()
                yield key, value

    @staticmethod
    def calc_version(prev_version: Optional[str] = None) -> str:
        dt = datetime.now().strftime("%Y%m%d")
        if prev_version is None:
            major, minor = dt, 0
        else:
            major, sep, minor = prev_version.partition('.')
            if major != dt:
                major, minor = dt, 0
            else:
                major, minor = dt, int(minor or '-1') + 1

        return f'{major}.{minor}'


@click.group()
@click.option("--instances",
              metavar="PATH",
              default="./instances/",
              help="instances/",
              type=ClickPath())
@click.option("--forge",
              metavar="PATH",
              default="./forge/",
              help="forge/",
              type=ClickPath())
@click.option("--packages",
              metavar="PATH",
              default="./web/packages/",
              help="web/packages/",
              type=ClickPath())
@click.option("--libraries",
              metavar="PATH",
              default="./web/libraries/",
              help="web/libraries/",
              type=ClickPath())
@click.option("--packages-url",
              metavar="URL",
              default=f"https://packages.{DOMAIN}/",
              help=f"https://packages.{DOMAIN}/")
@click.option("--libraries-url",
              metavar="URL",
              default=f"https://libraries.{DOMAIN}/",
              help=f"https://libraries.{DOMAIN}/")
@click.option("--use-requests-cache/--no-requests-cache",
              default=True,
              help="Use requests-cache")
@click.option("--use-cwd/--no-cwd",
              default=False,
              help="False; Use cwd when enabled")
@click.pass_context
def cli(ctx: Context,
        instances: Path,
        forge: Path,
        packages: Path,
        libraries: Path,
        libraries_url: str,
        packages_url: str,
        use_requests_cache: bool,
        use_cwd: bool):
    if not use_cwd:
        file = Path(__file__)
        if file.suffix == ".pyc":
            dir = file.parents[2]
        elif file.suffix == ".py":
            dir = file.parents[1]
        else:
            raise NotImplementedError(file.suffix)

        os.chdir(dir)

    print("cwd =", Path.cwd())

    ctx.obj = SUpdate(
        instances_path=instances.absolute(),
        forge_path=forge.absolute(),
        packages_path=packages.absolute(),
        libraries_path=libraries.absolute(),
        packages_url=packages_url,
        libraries_url=libraries_url,
    )

    if use_requests_cache:
        requests_cache.install_cache(".supdate")


if TYPE_CHECKING:
    cli: Cli


@cli.command("forge", help="internal command; pre-install forge", hidden=True)
@click.argument("version")
@click.pass_obj
def cli_forge(supdate: SUpdate, version: str):
    print(supdate.cmd_forge(version))


@cli.command("package", help="packaging modpack from instances/")
@click.argument("name")
@click.option("--forge-version")
@click.option("--force-update-forge/--no-update-forge", default=None)
@click.pass_obj
def cli_package(supdate: SUpdate, name: str, forge_version: Optional[str], force_update_forge: Optional[bool]):
    print(supdate.cmd_package(name, forge_version, force_update_forge))


@cli.command("update", help="update index from web/packages/")
@click.pass_obj
def cli_update(supdate: SUpdate):
    print(supdate.cmd_update())


@cli.command("build-pyz", hidden=not __file__.endswith('.py'))
def cli_build_pyz():
    this = Path(__file__)
    if this.suffix != ".py":
        raise Exception("can't packaging because already packaged")

    folder = this.parent
    target_folder = Path(tempfile.mkdtemp())

    shutil.copytree(folder, target_folder / folder.name)
    (target_folder / folder.name / "__main__.py").rename(target_folder / "__main__.py")

    compileall.compile_dir(target_folder, legacy=True)

    def filter_func(file: Path):
        if "__pycache__" in file.parts:
            return False

        return file.suffix == ".pyc"

    pyz_path = folder.with_suffix(".pyz")

    zipapp.create_archive(
        target_folder,
        pyz_path,
        "/usr/bin/env python3.9",
        filter=filter_func,
    )

    shutil.rmtree(target_folder)
    print(pyz_path)
