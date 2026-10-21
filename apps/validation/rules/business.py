"""Layer 2 – business rules: structure, integrity and lifecycle of the sequence."""
import re

from django.utils.translation import gettext_lazy as _

from ..ectd import MODULES, OPERATIONS, SEQUENCE_RE, heading_label, local_name, parse_modified_file
from .base import Layer, Rule, Severity

FOLDER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9]+$")
MAX_NAME_LENGTH = 64
MAX_PATH_LENGTH = 180

# Modules that must contain at least one document in the initial sequence (0000).
REQUIRED_MODULES = {
    "NEW_DRUG": ["m1", "m2", "m3", "m4", "m5"],
    "GENERIC": ["m1", "m2", "m3", "m5"],
    "VARIATION": ["m1"],
    "RENEWAL": ["m1"],
}


class SequenceNumber(Rule):
    code = "BR-01"
    layer = Layer.BUSINESS
    title = _("The package must contain one sequence folder with the expected 4-digit number")

    def check(self, ctx):
        if ctx.folder_name is None:
            yield self.issue("The package must contain exactly one top-level sequence folder such as 0000/.")
        elif not SEQUENCE_RE.match(ctx.folder_name):
            yield self.issue(f"Sequence folder '{ctx.folder_name}' is not a 4-digit number.")
        elif ctx.folder_name != ctx.expected_number:
            yield self.issue(
                f"Sequence folder is {ctx.folder_name}, but the next expected sequence for this "
                f"application is {ctx.expected_number}."
            )


class IndexChecksum(Rule):
    code = "BR-02"
    layer = Layer.BUSINESS
    title = _("index-md5.txt must exist and match the MD5 checksum of index.xml")

    def check(self, ctx):
        if not ctx.index_path.is_file():
            return
        md5_file = ctx.seq_dir / "index-md5.txt"
        if not md5_file.is_file():
            yield self.issue("index-md5.txt was not found next to index.xml.", file_path="index-md5.txt")
            return
        content = md5_file.read_text(encoding="ascii", errors="replace").strip()
        declared = content.split()[0].lower() if content else ""
        actual = ctx.md5(ctx.index_path)
        if declared != actual:
            yield self.issue(
                f"index-md5.txt declares '{declared or '(empty)'}' but index.xml has MD5 {actual}.",
                file_path="index-md5.txt",
            )


class LeafTargetsExist(Rule):
    code = "BR-03"
    layer = Layer.BUSINESS
    title = _("Every document reference (leaf) must point to a file inside the sequence")
    requires_index = True

    def check(self, ctx):
        for leaf in ctx.leaves:
            if leaf.operation == "delete":
                continue
            if not leaf.href:
                yield self.issue(f"Leaf '{leaf.id}' has no xlink:href.", location=leaf.location)
                continue
            target = ctx.resolve_href(leaf)
            if target is None:
                yield self.issue(
                    f"Leaf '{leaf.id}' href '{leaf.href}' must be a relative path inside the sequence.",
                    location=leaf.location,
                )
            elif not target.is_file():
                yield self.issue(
                    f"Leaf '{leaf.id}' points to '{leaf.href}', which does not exist.",
                    file_path=leaf.href,
                    location=leaf.location,
                )


class LeafChecksums(Rule):
    code = "BR-04"
    layer = Layer.BUSINESS
    title = _("Every document's MD5 checksum must match the value declared in the XML")
    requires_index = True

    def check(self, ctx):
        for leaf in ctx.leaves:
            if leaf.operation == "delete":
                continue
            target = ctx.resolve_href(leaf)
            if target is None or not target.is_file():
                continue  # reported by BR-03
            if leaf.checksum_type.lower() != "md5":
                yield self.issue(
                    f"Leaf '{leaf.id}' uses checksum-type '{leaf.checksum_type}'; only md5 is accepted.",
                    file_path=ctx.rel(target),
                    location=leaf.location,
                )
                continue
            actual = ctx.md5(target)
            if leaf.checksum.lower() != actual:
                yield self.issue(
                    f"Declared checksum {leaf.checksum or '(empty)'} but the file's MD5 is {actual}.",
                    file_path=ctx.rel(target),
                    location=leaf.location,
                )


class NoUnreferencedFiles(Rule):
    code = "BR-05"
    layer = Layer.BUSINESS
    severity = Severity.WARNING
    title = _("Files in the package should be referenced by the XML backbone")
    requires_index = True

    def check(self, ctx):
        referenced = {ctx.index_path.resolve(), (ctx.seq_dir / "index-md5.txt").resolve(), ctx.regional_path.resolve()}
        for leaf in ctx.leaves:
            target = ctx.resolve_href(leaf)
            if target is not None:
                referenced.add(target)
        for path in ctx.files:
            rel = ctx.rel(path)
            if rel.startswith("util/") or path.resolve() in referenced:
                continue
            yield self.issue("This file is not referenced by any leaf.", file_path=rel)


class RequiredModules(Rule):
    code = "BR-06"
    layer = Layer.BUSINESS
    title = _("The modules required for this application type must contain documents")
    requires_index = True

    def check(self, ctx):
        required = REQUIRED_MODULES.get(ctx.application_type, ["m1"]) if ctx.is_initial else ["m1"]
        root = ctx.index_tree.getroot()
        present = set()
        for module in root:
            name = local_name(module)
            if name and any(local_name(el) == "leaf" for el in module.iter()):
                present.add(name)
        for key in required:
            if MODULES[key] not in present:
                yield self.issue(
                    f"{heading_label(MODULES[key])} contains no documents.", file_path="index.xml"
                )


class LifecycleOperations(Rule):
    code = "BR-07"
    layer = Layer.BUSINESS
    title = _("Lifecycle operations must be valid and refer to documents in earlier sequences")
    requires_index = True

    def check(self, ctx):
        for leaf in ctx.leaves:
            if leaf.operation not in OPERATIONS:
                yield self.issue(
                    f"Leaf '{leaf.id}' has invalid operation '{leaf.operation}'.", location=leaf.location
                )
                continue
            if leaf.operation == "new":
                if leaf.modified_file:
                    yield self.issue(
                        f"Leaf '{leaf.id}' is 'new' but declares a modified-file.", location=leaf.location
                    )
                continue
            yield from self._check_modified_file(ctx, leaf)

    def _check_modified_file(self, ctx, leaf):
        if not leaf.modified_file:
            yield self.issue(
                f"Leaf '{leaf.id}' uses '{leaf.operation}' but has no modified-file.", location=leaf.location
            )
            return
        reference = parse_modified_file(leaf.modified_file)
        if reference is None:
            yield self.issue(
                f"modified-file '{leaf.modified_file}' must look like ../0000/index.xml#leaf-id.",
                location=leaf.location,
            )
            return
        number, path, leaf_id = reference
        current = ctx.folder_name if ctx.folder_name and SEQUENCE_RE.match(ctx.folder_name) else ctx.expected_number
        if number >= current:
            yield self.issue(
                f"modified-file refers to sequence {number}, which is not earlier than {current}.",
                location=leaf.location,
            )
            return
        previous_dir = ctx.previous.get(number)
        if previous_dir is None:
            yield self.issue(
                f"Sequence {number} has not been accepted for this application.", location=leaf.location
            )
            return
        tree = ctx.previous_tree(previous_dir / path)
        if tree is None:
            yield self.issue(f"{number}/{path} could not be read.", location=leaf.location)
            return
        targets = [el for el in tree.iter() if local_name(el) == "leaf" and el.get("ID") == leaf_id]
        if not targets:
            yield self.issue(f"No leaf with ID '{leaf_id}' exists in {number}/{path}.", location=leaf.location)
        elif targets[0].get("operation") == "delete":
            yield self.issue(f"Leaf '{leaf_id}' in sequence {number} was already deleted.", location=leaf.location)


class NamingConventions(Rule):
    code = "BR-08"
    layer = Layer.BUSINESS
    title = _("File and folder names must follow ICH naming conventions")

    def check(self, ctx):
        prefix = ctx.folder_name or ""
        for path in [*ctx.dirs, *ctx.files]:
            rel = ctx.rel(path)
            name = path.name
            pattern = FILE_NAME_RE if path.is_file() else FOLDER_NAME_RE
            full_length = len(f"{prefix}/{rel}") if prefix else len(rel)
            if not pattern.match(name):
                yield self.issue(
                    f"'{name}' must use only lowercase letters, digits and hyphens"
                    + (" with a single extension." if path.is_file() else "."),
                    file_path=rel,
                )
            elif len(name) > MAX_NAME_LENGTH:
                yield self.issue(f"Name is {len(name)} characters; the maximum is {MAX_NAME_LENGTH}.", file_path=rel)
            elif full_length > MAX_PATH_LENGTH:
                yield self.issue(
                    f"Path is {full_length} characters; the maximum is {MAX_PATH_LENGTH}.", file_path=rel
                )


class UtilFolder(Rule):
    code = "BR-09"
    layer = Layer.BUSINESS
    title = _("The util/dtd folder must contain the eCTD DTD")

    def check(self, ctx):
        if not (ctx.seq_dir / "util" / "dtd" / "ich-ectd-3-2.dtd").is_file():
            yield self.issue("util/dtd/ich-ectd-3-2.dtd was not found.", file_path="util/dtd/")


class DistinctLeafTitles(Rule):
    """Two documents filed in one place under one title are indistinguishable to the reviewer.

    Scoped to the element holding the leaves, which is exactly the group the dossier viewer lists
    under a single node: the Arabic and English leaflets, for instance, sit under a pi-doc of their
    own each, so the same title there is not a clash. Neither the ICH eCTD 3.2 DTD nor the GCC
    Module 1 leaf module requires titles to be unique, so this is a warning.
    """

    code = "BR-10"
    layer = Layer.BUSINESS
    severity = Severity.WARNING
    title = _("Documents filed in the same place should have titles that tell them apart")
    requires_index = True

    def check(self, ctx):
        groups: dict[tuple, list] = {}
        for leaf in ctx.leaves:
            # A delete keeps the title of the document it withdraws, and an untitled leaf is shown
            # by its file name, so neither can be confused with another document.
            if leaf.operation == "delete" or not leaf.title.strip():
                continue
            key = (leaf.source, leaf.parent, " ".join(leaf.title.split()).casefold())
            groups.setdefault(key, []).append(leaf)

        for leaves in groups.values():
            if len(leaves) < 2:
                continue
            names = [leaf.href or leaf.id for leaf in leaves]
            listed = ", ".join(names[:4]) + (f" (+{len(names) - 4} more)" if len(names) > 4 else "")
            yield self.issue(
                f"{len(leaves)} documents in the same section are titled '{leaves[0].title.strip()}': {listed}.",
                location=leaves[0].location,
            )


RULES = [
    SequenceNumber(),
    IndexChecksum(),
    LeafTargetsExist(),
    LeafChecksums(),
    NoUnreferencedFiles(),
    RequiredModules(),
    LifecycleOperations(),
    NamingConventions(),
    UtilFolder(),
    DistinctLeafTitles(),
]
