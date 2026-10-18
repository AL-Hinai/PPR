"""Everything the rules need to know about one extracted sequence, parsed once."""
import hashlib
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

from .ectd import ECTD_32, Leaf, detect_backbone, local_name, locate_sequence_dir, parse_xml
from .pdf import PdfReport, inspect_pdf
from .regions import get_profile
from .regions.gcc import parse_envelopes, select_envelope


@dataclass
class Limits:
    max_file_bytes: int


@dataclass
class ValidationContext:
    root: Path  # extraction folder
    expected_number: str
    application_type: str
    region: str
    dtd_path: Path
    limits: Limits
    previous: dict[str, Path] = field(default_factory=dict)  # accepted sequence no. -> its folder
    country: str = "om"  # receiving country (ECTD_COUNTRY), as in the GCC envelope

    def __post_init__(self):
        self.region_profile = get_profile(self.region)
        # Resolved, so rel() works on resolved hrefs even when the root is a short (8.3) or symlinked path.
        self.root = Path(self.root).resolve()
        self.seq_dir, self.folder_name = locate_sequence_dir(self.root)
        self.backbone = detect_backbone(self.seq_dir)  # "3.2.2", "4.0" (not accepted) or ""
        self.reader = ECTD_32
        self.index_path = self.seq_dir / "index.xml"
        self.index_error = ""
        self.index_error_line = None
        self.regional_error = ""
        self._md5_cache: dict[Path, str] = {}
        self._pdf_cache: dict[Path, PdfReport] = {}
        self._previous_trees: dict[Path, object] = {}

    # --- paths -------------------------------------------------------------
    @property
    def is_initial(self):
        return self.expected_number == "0000"

    @property
    def display_folder(self):
        return self.folder_name or "(root)"

    def rel(self, path: Path) -> str:
        return path.relative_to(self.seq_dir).as_posix()

    @cached_property
    def files(self) -> list[Path]:
        return sorted(p for p in self.seq_dir.rglob("*") if p.is_file())

    @cached_property
    def dirs(self) -> list[Path]:
        return sorted(p for p in self.seq_dir.rglob("*") if p.is_dir())

    @property
    def regional_rel(self) -> str:
        return self.region_profile.regional_rel

    @property
    def regional_path(self) -> Path:
        return self.seq_dir / self.regional_rel

    # --- XML -----------------------------------------------------------------
    @cached_property
    def index_tree(self):
        if not self.index_path.is_file():
            return None
        try:
            return parse_xml(self.index_path)
        except etree.XMLSyntaxError as exc:
            self.index_error = str(exc)
            self.index_error_line = exc.lineno
            return None

    @cached_property
    def regional_tree(self):
        if not self.regional_path.is_file():
            return None
        try:
            return parse_xml(self.regional_path)
        except etree.XMLSyntaxError as exc:
            self.regional_error = str(exc)
            return None

    @property
    def regional_root_ok(self) -> bool:
        """The regional XML has the root element and namespace the region's specification requires."""
        if self.regional_tree is None:
            return False
        root = self.regional_tree.getroot()
        profile = self.region_profile
        return local_name(root) == profile.root_element and etree.QName(root).namespace == profile.namespace

    @cached_property
    def envelopes(self) -> list[dict]:
        return parse_envelopes(self.regional_tree) if self.regional_tree is not None else []

    @cached_property
    def envelope(self) -> dict | None:
        """The submission envelope addressed to the receiving country (or to all GCC countries)."""
        return select_envelope(self.envelopes, self.country)

    @cached_property
    def leaves(self) -> list[Leaf]:
        leaves = []
        if self.index_tree is not None:
            leaves += self.reader.leaves(self.index_tree, "index.xml", self.seq_dir)
        if self.regional_tree is not None:
            leaves += self.reader.leaves(self.regional_tree, self.regional_rel, self.regional_path.parent)
        return leaves

    def resolve_href(self, leaf: Leaf) -> Path | None:
        """The file a leaf points to, or None if the href is unusable / outside the sequence."""
        href = leaf.href.strip()
        if not href or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href) or href.startswith(("/", "\\")):
            return None
        target = (leaf.base_dir / unquote(href)).resolve()
        if not target.is_relative_to(self.seq_dir.resolve()):
            return None
        return target

    def previous_tree(self, path: Path):
        if path not in self._previous_trees:
            try:
                self._previous_trees[path] = parse_xml(path)
            except (etree.XMLSyntaxError, OSError):
                self._previous_trees[path] = None
        return self._previous_trees[path]

    # --- file helpers ----------------------------------------------------------
    def md5(self, path: Path) -> str:
        if path not in self._md5_cache:
            digest = hashlib.md5()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            self._md5_cache[path] = digest.hexdigest()
        return self._md5_cache[path]

    def pdf(self, path: Path) -> PdfReport:
        if path not in self._pdf_cache:
            self._pdf_cache[path] = inspect_pdf(path)
        return self._pdf_cache[path]

    @property
    def pdf_files(self) -> list[Path]:
        return [p for p in self.files if p.suffix.lower() == ".pdf" and p.stat().st_size > 0]
