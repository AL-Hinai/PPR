"""GCC Module 1 rules (GCC Module 1 Specifications v1.5): regional XML, envelope and Module 1 content."""
from pathlib import PurePosixPath

from django.utils.translation import gettext_lazy as _

from ..ectd import SEQUENCE_RE
from ..regions import gcc
from .base import Layer, Rule, Severity
from .schema import MAX_DTD_ERRORS, load_dtd


class GccRule(Rule):
    """Runs only for the GCC region, once the regional XML has been parsed (SCH-04 reports otherwise)."""

    needs_envelope = False

    def applies(self, ctx) -> bool:
        if ctx.region_profile is not gcc.GCC or not ctx.regional_root_ok or not super().applies(ctx):
            return False
        return ctx.envelope is not None or not self.needs_envelope


class RegionalRoot(Rule):
    code = "GCC-01"
    layer = Layer.SCHEMA
    title = _("The GCC regional XML must have the gc:gc-backbone root in the http://sfda.gov.sa namespace")

    def applies(self, ctx) -> bool:
        return ctx.region_profile is gcc.GCC and ctx.regional_tree is not None

    def check(self, ctx):
        if not ctx.regional_root_ok:
            root = ctx.regional_tree.getroot()
            yield self.issue(
                f"The root element is {root.tag}; expected gc-backbone in namespace {gcc.GCC.namespace}.",
                file_path=ctx.regional_rel,
            )


class RegionalMatchesDtd(GccRule):
    code = "GCC-02"
    layer = Layer.SCHEMA
    title = _("The GCC regional XML must be valid against the GCC regional DTD")

    def check(self, ctx):
        path = ctx.region_profile.dtd_path
        if not path.is_file():
            yield self.issue(f"The GCC regional DTD is missing on the server: {path}")
            return
        dtd = load_dtd(path)
        if dtd.validate(ctx.regional_tree):
            return
        for error in list(dtd.error_log)[:MAX_DTD_ERRORS]:
            yield self.issue(error.message, file_path=ctx.regional_rel, location=f"line {error.line}")


class EnvelopeAgency(GccRule):
    code = "GCC-03"
    layer = Layer.BUSINESS
    title = _("The envelope must be addressed to the receiving country and its agency")

    def check(self, ctx):
        agency = gcc.AGENCIES.get(ctx.country, "")
        envelope = ctx.envelope
        if envelope is None:
            found = ", ".join(sorted({e["country"] for e in ctx.envelopes})) or "none"
            yield self.issue(
                f"No envelope for country '{ctx.country}' (or 'common'); envelopes found for: {found}.",
                file_path=ctx.regional_rel,
            )
        elif envelope.get("agency") != agency:
            yield self.issue(
                f"The envelope for '{envelope['country']}' names agency {envelope.get('agency') or '(none)'}; "
                f"this submission is received by {agency}.",
                file_path=ctx.regional_rel,
                location=f"line {envelope['line']}",
            )


class EnvelopeSequence(GccRule):
    code = "GCC-04"
    layer = Layer.BUSINESS
    title = _("The envelope sequence and related sequences must match this application's lifecycle")
    needs_envelope = True

    def check(self, ctx):
        envelope = ctx.envelope
        where = {"file_path": ctx.regional_rel, "location": f"line {envelope['line']}"}
        if envelope.get("sequence") != ctx.expected_number:
            yield self.issue(
                f"The envelope gives sequence '{envelope.get('sequence', '')}', but this submission is "
                f"sequence {ctx.expected_number}.",
                **where,
            )
        for related in envelope["related_sequences"]:
            if not SEQUENCE_RE.match(related) or related >= ctx.expected_number:
                yield self.issue(f"Related sequence '{related}' is not an earlier sequence.", **where)
            elif related not in ctx.previous:
                yield self.issue(f"Related sequence {related} is not an accepted sequence of this application.", **where)


class SubmissionType(GccRule):
    code = "GCC-05"
    layer = Layer.BUSINESS
    title = _("The envelope submission type must match the application type")
    needs_envelope = True

    def check(self, ctx):
        submission_type = ctx.envelope.get("submission_type", "")
        allowed = gcc.SUBMISSION_TYPES.get(ctx.application_type, ())
        if submission_type != "none" and submission_type not in allowed:
            yield self.issue(
                f"Submission type '{submission_type}' does not fit a {ctx.application_type.replace('_', ' ').lower()} "
                f"application; expected {' or '.join(allowed)}.",
                file_path=ctx.regional_rel,
                location=f"line {ctx.envelope['line']}",
            )


class SubmissionUnit(GccRule):
    code = "GCC-06"
    layer = Layer.BUSINESS
    title = _("The envelope submission unit must fit the sequence")
    needs_envelope = True

    def check(self, ctx):
        unit = ctx.envelope.get("submission_unit", "")
        submission_type = ctx.envelope.get("submission_type", "")
        where = {"file_path": ctx.regional_rel, "location": f"line {ctx.envelope['line']}"}
        if (unit == "reformat") != (submission_type == "none"):
            yield self.issue("Submission unit 'reformat' must be used together with submission type 'none'.", **where)
        elif ctx.is_initial and unit not in ("initial", "reformat"):
            yield self.issue(f"Sequence 0000 must be an 'initial' (or 'reformat') submission unit, not '{unit}'.", **where)
        elif not ctx.is_initial and unit == "initial":
            yield self.issue(
                "Later sequences answer information requests: use the 'response' or 'additional-info' unit.",
                severity=Severity.WARNING,
                **where,
            )


class RequiredModule1Documents(GccRule):
    code = "GCC-07"
    layer = Layer.BUSINESS
    title = _("Module 1 must contain the documents required for this submission")

    def check(self, ctx):
        if ctx.is_initial:
            required = gcc.REQUIRED_INITIAL.get(ctx.application_type, [])
        else:
            required = gcc.REQUIRED_FOLLOW_UP
        for element in required:
            if not gcc.section_documents(ctx.regional_tree, element, ctx.country):
                yield self.issue(
                    f"{gcc.HEADINGS.get(element, element)} has no document for country '{ctx.country}'.",
                    file_path=ctx.regional_rel,
                )
        if "m1-3-3-pil" in required:
            languages = gcc.leaflet_languages(ctx.regional_tree, ctx.country)
            for language in gcc.PIL_LANGUAGES:
                if language not in languages:
                    yield self.issue(
                        f"1.3.3 Patient information leaflet in {gcc.LANGUAGE_NAMES[language]} is missing.",
                        file_path=ctx.regional_rel,
                    )


class RegionalLeafOperation(GccRule):
    code = "GCC-08"
    layer = Layer.BUSINESS
    title = _("index.xml must reference the GCC regional XML with operation 'new'")
    requires_index = True

    def check(self, ctx):
        regional = PurePosixPath(ctx.regional_rel)
        leaves = [
            leaf for leaf in ctx.leaves
            if leaf.source == "index.xml" and PurePosixPath(leaf.href.strip()) == regional
        ]
        if not leaves:
            yield self.issue(f"index.xml has no leaf pointing to {ctx.regional_rel}.", file_path="index.xml")
        for leaf in leaves:
            if leaf.operation != "new":
                yield self.issue(
                    f"The leaf for {ctx.regional_rel} has operation '{leaf.operation}'; it must always be 'new'.",
                    file_path="index.xml",
                    location=leaf.location,
                )


class RegionalDtdFiles(GccRule):
    code = "GCC-09"
    layer = Layer.BUSINESS
    title = _("The GCC regional DTD files must be included in util/dtd")

    def check(self, ctx):
        folders = [ctx.seq_dir / "util" / "dtd", ctx.regional_path.parent / "util" / "dtd"]
        for name in ctx.region_profile.dtd_files:
            if not any((folder / name).is_file() for folder in folders):
                yield self.issue(f"util/dtd/{name} is missing.", file_path=f"util/dtd/{name}")


SCHEMA_RULES = [RegionalRoot(), RegionalMatchesDtd()]
BUSINESS_RULES = [
    EnvelopeAgency(),
    EnvelopeSequence(),
    SubmissionType(),
    SubmissionUnit(),
    RequiredModule1Documents(),
    RegionalLeafOperation(),
    RegionalDtdFiles(),
]
