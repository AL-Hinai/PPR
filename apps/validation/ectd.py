"""eCTD constants and XML helpers shared by the validator, the dossier viewer and the sample builder."""
import re
from pathlib import Path

from lxml import etree

ECTD_NS = "http://www.ich.org/ectd"
# The ICH eCTD 3.2 specification uses this (non-standard) XLink namespace.
XLINK_NS = "http://www.w3c.org/1999/xlink"
SEQUENCE_RE = re.compile(r"^\d{4}$")
OPERATIONS = ("new", "append", "replace", "delete")

MODULES = {
    "m1": "m1-administrative-information-and-prescribing-information",
    "m2": "m2-common-technical-document-summaries",
    "m3": "m3-quality",
    "m4": "m4-nonclinical-study-reports",
    "m5": "m5-clinical-study-reports",
}


def safe_parser():
    """An XML parser that never loads external entities, DTDs or network resources."""
    return etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False
    )


def parse_xml(path: Path):
    return etree.parse(str(path), safe_parser())


def local_name(element) -> str:
    if not isinstance(element.tag, str):
        return ""
    return etree.QName(element).localname


def attr(element, name: str) -> str:
    """Attribute by local name, ignoring its namespace (xlink:href, href, …)."""
    for key, value in element.attrib.items():
        if key == name or key.endswith("}" + name):
            return value
    return ""


def child_text(element, name: str) -> str:
    for child in element:
        if local_name(child) == name:
            return (child.text or "").strip()
    return ""


def heading_label(tag: str) -> str:
    """'m3-2-p-5-control-of-drug-product' -> '3.2.P.5 Control of drug product'."""
    parts = tag.split("-")
    if not parts or not re.fullmatch(r"m\d", parts[0]):
        return tag.replace("-", " ").capitalize()
    numbers = [parts[0][1:]]
    i = 1
    while i < len(parts) and (parts[i].isdigit() or (len(parts[i]) == 1 and parts[i].isalpha())):
        numbers.append(parts[i].upper())
        i += 1
    words = " ".join(parts[i:]).capitalize()
    return f"{'.'.join(numbers)} {words}".strip()


def locate_sequence_dir(root: Path) -> tuple[Path, str | None]:
    """Find the sequence folder (e.g. ``0000``) inside an extracted package.

    Accepts ``0000/…`` at the top level or wrapped in one product folder.
    Returns (folder, folder_name); folder_name is None when no single
    sequence folder exists.
    """
    if (root / "index.xml").is_file():
        return root, None
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    dirs = [p for p in entries if p.is_dir()]
    sequences = [d for d in dirs if SEQUENCE_RE.match(d.name)]
    if len(sequences) == 1:
        return sequences[0], sequences[0].name
    if len(dirs) == 1 and not sequences:
        inner = [p for p in dirs[0].iterdir() if p.is_dir() and SEQUENCE_RE.match(p.name)]
        if len(inner) == 1:
            return inner[0], inner[0].name
        if (dirs[0] / "index.xml").is_file():
            return dirs[0], dirs[0].name
    return root, None


# --- Dossier tree for the reviewer's viewer ---------------------------------

def _leaf_info(leaf, base_dir: Path, seq_dir: Path) -> dict:
    href = attr(leaf, "href")
    rel = ""
    if href:
        target = (base_dir / href).resolve()
        if target.is_relative_to(seq_dir.resolve()):
            rel = target.relative_to(seq_dir.resolve()).as_posix()
    return {
        "id": leaf.get("ID", ""),
        "title": child_text(leaf, "title") or href or leaf.get("ID", ""),
        "operation": leaf.get("operation", ""),
        "path": rel,
        "exists": bool(rel) and (seq_dir / rel).is_file(),
        "is_pdf": rel.lower().endswith(".pdf"),
    }


def _node_label(element) -> str:
    from .regions.gcc import COUNTRY_NAMES, HEADINGS, LANGUAGE_NAMES

    name = local_name(element)
    if name == "node-extension":
        return child_text(element, "title") or name
    if name in HEADINGS:
        return HEADINGS[name]
    if name in ("specific", "pi-doc"):  # GCC country (and language) containers
        country = COUNTRY_NAMES.get(element.get("country", ""), element.get("country", ""))
        lang = element.get("{http://www.w3.org/XML/1998/namespace}lang", "")
        return f"{country} – {LANGUAGE_NAMES.get(lang, lang)}" if lang else country
    label = heading_label(name)
    extras = [element.get(a) for a in ("substance", "product-name", "dosageform", "manufacturer", "indication", "excipient")]
    extras = [e for e in extras if e]
    return f"{label} — {', '.join(extras)}" if extras else label


def _build_node(element, base_dir: Path, seq_dir: Path, depth=0) -> dict | None:
    node = {"label": _node_label(element), "leaves": [], "children": [], "depth": depth}
    for child in element:
        name = local_name(child)
        if not name or name == "title":
            continue
        if name == "leaf":
            info = _leaf_info(child, base_dir, seq_dir)
            node["leaves"].append(info)
            if info["path"].endswith("-regional.xml") and info["exists"]:
                regional = _regional_tree(seq_dir / info["path"], seq_dir, depth + 1)
                if regional:
                    node["children"].append(regional)
        else:
            sub = _build_node(child, base_dir, seq_dir, depth + 1)
            if sub:
                node["children"].append(sub)
    if not node["leaves"] and not node["children"]:
        return None
    return node


def _regional_tree(path: Path, seq_dir: Path, depth: int) -> dict | None:
    try:
        root = parse_xml(path).getroot()
    except (etree.XMLSyntaxError, OSError):
        return None
    node = _build_node(root, path.parent, seq_dir, depth)
    if node and len(node["children"]) == 1 and not node["leaves"]:
        node = node["children"][0]  # skip the backbone root: show "Module 1 – GCC regional information" directly
        _shift_depth(node, depth)
    elif node:
        node["label"] = "Regional information (" + path.name.replace("-regional.xml", "").upper() + ")"
    return node


def _shift_depth(node: dict, depth: int) -> None:
    node["depth"] = depth
    for child in node["children"]:
        _shift_depth(child, depth + 1)


def build_dossier_tree(seq_dir: Path) -> list[dict]:
    """Nested CTD headings with their documents, built from index.xml."""
    index = seq_dir / "index.xml"
    try:
        root = parse_xml(index).getroot()
    except (etree.XMLSyntaxError, OSError):
        return []
    modules = []
    for module in root:
        node = _build_node(module, seq_dir, seq_dir) if local_name(module) else None
        if node:
            modules.append(node)
    return modules
