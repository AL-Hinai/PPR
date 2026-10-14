"""Layer 1 – XML schema validation of the eCTD backbone."""
from pathlib import Path

from django.utils.translation import gettext_lazy as _
from lxml import etree

from .base import Layer, Rule

MAX_DTD_ERRORS = 50
_dtd_cache: dict[tuple[str, float], etree.DTD] = {}


def load_dtd(path: Path) -> etree.DTD:
    key = (str(path), path.stat().st_mtime)
    if key not in _dtd_cache:
        with open(path, "rb") as fh:
            _dtd_cache[key] = etree.DTD(fh)
    return _dtd_cache[key]


class IndexExists(Rule):
    code = "SCH-01"
    layer = Layer.SCHEMA
    title = _("The sequence must contain an index.xml backbone file")

    def check(self, ctx):
        if not ctx.index_path.is_file():
            yield self.issue(
                "index.xml was not found in the sequence folder.",
                file_path=f"{ctx.display_folder}/index.xml",
            )


class IndexWellFormed(Rule):
    code = "SCH-02"
    layer = Layer.SCHEMA
    title = _("index.xml must be well-formed XML")

    def check(self, ctx):
        if ctx.index_path.is_file() and ctx.index_tree is None:
            line = f"line {ctx.index_error_line}" if ctx.index_error_line else ""
            yield self.issue(ctx.index_error, file_path="index.xml", location=line)


class IndexMatchesDtd(Rule):
    code = "SCH-03"
    layer = Layer.SCHEMA
    title = _("index.xml must be valid against the ICH eCTD 3.2 DTD")
    requires_index = True

    def check(self, ctx):
        if not ctx.dtd_path.is_file():
            yield self.issue(f"The reference DTD is missing on the server: {ctx.dtd_path}")
            return
        dtd = load_dtd(ctx.dtd_path)
        if dtd.validate(ctx.index_tree):
            return
        for error in list(dtd.error_log)[:MAX_DTD_ERRORS]:
            yield self.issue(error.message, file_path="index.xml", location=f"line {error.line}")


class RegionalXml(Rule):
    code = "SCH-04"
    layer = Layer.SCHEMA
    title = _("The regional Module 1 XML must exist and be well-formed")

    def check(self, ctx):
        if not ctx.regional_path.is_file():
            yield self.issue(
                f"Expected regional file {ctx.regional_rel} was not found.", file_path=ctx.regional_rel
            )
        elif ctx.regional_tree is None:
            yield self.issue(ctx.regional_error, file_path=ctx.regional_rel)


RULES = [IndexExists(), IndexWellFormed(), IndexMatchesDtd(), RegionalXml()]
