from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegionProfile:
    code: str  # value of ECTD_REGION
    name: str
    folder: str  # m1/<folder>/
    regional_file: str  # the regional backbone inside m1/<folder>/
    namespace: str
    root_element: str  # local name of the regional XML root
    dtd_dir: Path  # bundled regional DTD and its modules
    dtd_file: str  # entry point inside dtd_dir
    dtd_files: tuple[str, ...]  # files the package must carry in util/dtd/

    @property
    def regional_rel(self) -> str:
        return f"m1/{self.folder}/{self.regional_file}"

    @property
    def dtd_path(self) -> Path:
        return self.dtd_dir / self.dtd_file
