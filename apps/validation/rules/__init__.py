"""Rule registry. Layers run in order: XML schema → business rules → file compliance."""
from . import business, files, regional, schema

ALL_RULES = [*schema.RULES, *regional.SCHEMA_RULES, *business.RULES, *regional.BUSINESS_RULES, *files.RULES]
RULES_BY_CODE = {rule.code: rule for rule in [*ALL_RULES, files.PACKAGE_RULE]}
