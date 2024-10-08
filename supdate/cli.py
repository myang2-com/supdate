import compileall
import json
import os
import shutil
import tempfile
import zipapp
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import urljoin

import click
import requests_cache
from click import Context
from click import Group as Cli

from .index import IndexPackage, IndexPackageManifest, Launcher
from .package import Package, PackageBuilder
from .providers.base import Provider
from .providers.fabric import FabricProvider
from .providers.forge import ForgeProvider
from .utils import sha1_hexdigest
from .versions import calc_next_version

DOMAIN = "myang2.com"


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
    provider: Optional[Provider] = None

    def __post_init__(self):
        self.libraries_url = self.libraries_url.rstrip("/")
        self.packages_url = self.packages_url.rstrip("/")
        self.current_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+0000")
        self.fabric_provider = FabricProvider()
        self.forge_provider = ForgeProvider(
            forge_path=self.forge_path,
            libraries_path=self.libraries_path,
            libraries_url=self.libraries_url,
        )

    @property
    def index_path(self):
        return self.packages_path / "index.json"

    def cmd_package(
        self,
        name: str,
        version: Optional[str] = None,
        *,
        force_build: bool = None,
    ) -> Path:
        instance_path = self.instances_path / name
        package_path = self.packages_path / name
        modpack_path = package_path / "modpack.json"
        client_path = instance_path / "client"

        if not instance_path.exists():
            raise FileNotFoundError(str(instance_path))

        if not client_path.exists():
            client_path.mkdir(exist_ok=True, parents=True)

        prev_manifest = self.get_latest_manifest()
        prev_package = (
            Package.read_from_path(modpack_path) if modpack_path.exists() else None
        )

        _, provider_profile = self.provider.auto_profile(
            instance_path=instance_path,
            version=version,
            force_build=force_build,
        )

        package = Package.from_profile(provider_profile)
        package.id = name
        package.name = prev_package.name if prev_package else name
        package.version = calc_next_version(prev_manifest.version)
        package.time = self.current_datetime

        assert not self.packages_url.endswith("/")
        package_url = f"{self.packages_url}/{name}/"

        package_builder = PackageBuilder(
            package, instance_path, package_path, package_url
        )
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

            if exclusion_key in exclusion and isinstance(
                exclusion[exclusion_key], list
            ):
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

        self.cmd_update()

        return modpack_path

    def cmd_update(self) -> Path:
        index_path = self.index_path

        prev_manifest = self.get_latest_manifest()
        next_version = calc_next_version(prev_manifest.version)
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

            prev_index_package = (
                prev_manifest.packages.get(package.id) if prev_manifest else None
            )
            if prev_index_package and prev_index_package.sha1 == sha1_hexdigest(
                modpack_path
            ):
                index_package = prev_index_package
            else:
                package.version = next_version
                package.time = next_datetime
                package.write_to_path(modpack_path)

                index_package = IndexPackage.from_package(
                    package=package,
                    modpack_path=modpack_path,
                    package_url=urljoin(self.packages_url, f"{package_path.name}/"),
                )

            manifest.packages[package.id] = index_package

        manifest.write_to_path(index_path)
        return index_path

    def get_latest_manifest(self) -> IndexPackageManifest:
        if self.index_path.exists():
            return IndexPackageManifest.read_from_path(self.index_path)
        else:
            return IndexPackageManifest(
                version=calc_next_version(),
                time=self.current_datetime,
                launcher=Launcher(
                    version="0.0.0",
                    url="https://example.com/",
                ),
            )


@click.group()
@click.option(
    "--instances",
    metavar="PATH",
    default="./instances/",
    help="instances/",
    type=ClickPath(),
)
@click.option("--provider", type=click.Choice(["fabric", "forge"]))
@click.option(
    "--forge", metavar="PATH", default="./forge/", help="forge/", type=ClickPath()
)
@click.option(
    "--packages",
    metavar="PATH",
    default="./web/packages/",
    help="web/packages/",
    type=ClickPath(),
)
@click.option(
    "--libraries",
    metavar="PATH",
    default="./web/libraries/",
    help="web/libraries/",
    type=ClickPath(),
)
@click.option(
    "--packages-url",
    metavar="URL",
    default=f"https://packages.{DOMAIN}/",
    help=f"https://packages.{DOMAIN}/",
)
@click.option(
    "--libraries-url",
    metavar="URL",
    default=f"https://libraries.{DOMAIN}/",
    help=f"https://libraries.{DOMAIN}/",
)
@click.option(
    "--use-requests-cache/--no-requests-cache", default=True, help="Use requests-cache"
)
@click.option("--use-cwd/--no-cwd", default=False, help="False; Use cwd when enabled")
@click.pass_context
def cli(
    ctx: Context,
    instances: Path,
    provider: str,
    forge: Path,
    packages: Path,
    libraries: Path,
    libraries_url: str,
    packages_url: str,
    use_requests_cache: bool,
    use_cwd: bool,
):
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

    ctx.obj.provider = {
        "fabric": ctx.obj.fabric_provider,
        "forge": ctx.obj.forge_provider,
    }.get(provider)

    if use_requests_cache:
        requests_cache.install_cache(".supdate")


if TYPE_CHECKING:
    cli: Cli


@cli.command("build-profile", help="build fabric/forge profile")
@click.argument("version")
@click.pass_obj
def cli_build_profile(supdate: SUpdate, version: str):
    profile_path, profile = supdate.provider.auto_profile(
        instance_path=supdate.instances_path,
        version=version,
        force_build=True,
    )
    print(profile_path)


@cli.command("package", help="packaging modpack from instances/")
@click.argument("name")
@click.option("--version")
@click.option("--force-build/--no-build", default=None)
@click.pass_obj
def cli_package(
    supdate: SUpdate,
    name: str,
    version: str,
    force_build: Optional[bool],
):
    print(
        supdate.cmd_package(
            name,
            version=version,
            force_build=force_build,
        )
    )


@cli.command("update", help="update index from web/packages/")
@click.pass_obj
def cli_update(supdate: SUpdate):
    print(supdate.cmd_update())


@cli.command("build-pyz", hidden=not __file__.endswith(".py"))
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
        "/usr/bin/env python3.11",
        filter=filter_func,
    )

    shutil.rmtree(target_folder)
    print(pyz_path)
