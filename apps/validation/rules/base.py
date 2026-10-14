from dataclasses import dataclass

from ..models import Finding

Layer = Finding.Layer
Severity = Finding.Severity


@dataclass
class Issue:
    rule_code: str
    layer: str
    severity: str
    detail: str = ""
    file_path: str = ""
    location: str = ""


class Rule:
    """One validation criterion. Subclasses implement ``check``."""

    code = ""
    layer = ""
    severity = Severity.ERROR
    title = ""
    # Skip the rule when index.xml is missing or malformed (Layer 1 already reported it).
    requires_index = False

    def applies(self, ctx) -> bool:
        return not self.requires_index or ctx.index_tree is not None

    def check(self, ctx):
        raise NotImplementedError

    def issue(self, detail="", file_path="", location="", severity=None) -> Issue:
        return Issue(
            rule_code=self.code,
            layer=self.layer,
            severity=severity or self.severity,
            detail=detail,
            file_path=file_path,
            location=location,
        )
