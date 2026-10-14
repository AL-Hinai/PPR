"""Rule registry. Layers run in order: XML schema → business rules → file compliance."""
from . import business, files, schema

ALL_RULES = [*schema.RULES, *business.RULES, *files.RULES]
RULES_BY_CODE = {rule.code: rule for rule in [*ALL_RULES, files.PACKAGE_RULE]}
