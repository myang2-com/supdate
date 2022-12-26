from __future__ import annotations

from pathlib import Path
from typing import Optional

from supdate.profile import Profile


class Provider:
    def auto_profile(
        self,
        instance_path: Path,
        version: Optional[str] = None,
        *,
        force_build: bool = False,
    ) -> tuple[Path, Profile]:
        raise NotImplementedError

    def get_profile(self, profile_path: Path) -> Profile:
        raise NotImplementedError

    def build_profile(self, vanilla_version: str, vendor_version: str) -> Profile:
        raise NotImplementedError
