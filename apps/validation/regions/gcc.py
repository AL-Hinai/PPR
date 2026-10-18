"""GCC Module 1 (GCC Module 1 Specifications v1.5, SFDA, November 2015).

The regional backbone is ``m1/gc/gc-regional.xml``: a ``gc:gc-backbone`` root with a
``gc-envelope`` (submission metadata, one ``envelope`` per receiving country) and the
``m1-gc`` table of contents.
"""
from pathlib import Path

from ..ectd import local_name
from .base import RegionProfile

GCC = RegionProfile(
    code="gcc",
    name="GCC",
    folder="gc",
    regional_file="gc-regional.xml",
    namespace="http://sfda.gov.sa",
    root_element="gc-backbone",
    dtd_dir=Path(__file__).resolve().parent.parent / "dtd" / "gcc",
    dtd_file="gc-regional.dtd",
    dtd_files=("gc-regional.dtd", "gc-envelope.mod", "gc-leaf.mod"),
)

# Appendix 5: receiving agency for each destination country.
AGENCIES = {
    "ae": "AE-MOH",
    "bh": "BH-MOH",
    "kw": "KW-MOH",
    "om": "OM-MOH",
    "qa": "QA-NHA",
    "sa": "SA-SFDA",
    "ye": "YE-MOPHP",
}
COUNTRY_NAMES = {
    "ae": "United Arab Emirates",
    "bh": "Bahrain",
    "kw": "Kuwait",
    "om": "Oman",
    "qa": "Qatar",
    "sa": "Saudi Arabia",
    "ye": "Yemen",
    "common": "All GCC countries",
}

# Envelope submission types that fit each PPR application type ("none" is only for reformatting).
SUBMISSION_TYPES = {
    "NEW_DRUG": ("new-nce", "new-bio", "new-rad"),
    "GENERIC": ("new-gen",),
    "VARIATION": ("var-type1", "var-type2", "extension"),
    "RENEWAL": ("renewal",),
}

# Module 1 sections that must hold at least one document for the receiving country.
# Based on the Oman MOH draft eCTD guideline (appendices 2 and 4) and GCC M1 v1.5 appendix 2;
# to be confirmed with the Drug Safety Center before go-live.
_NEW_PRODUCT = ["m1-0-cover", "m1-2-form", "m1-3-1-spc", "m1-3-2-label", "m1-3-3-pil", "m1-7-1-gmp", "m1-8-1-price-list"]
REQUIRED_INITIAL = {
    "NEW_DRUG": _NEW_PRODUCT,
    "GENERIC": _NEW_PRODUCT,
    "VARIATION": ["m1-0-cover", "m1-2-form"],
    "RENEWAL": ["m1-0-cover", "m1-2-form", "m1-8-1-price-list"],
}
REQUIRED_FOLLOW_UP = ["m1-0-cover", "m1-9-responses"]  # later sequences answer information requests
PIL_LANGUAGES = ("ar", "en")

# Appendix 2 headings, for findings and the dossier viewer.
HEADINGS = {
    "m1-gc": "Module 1 – GCC regional information",
    "m1-0-cover": "1.0 Cover letter",
    "m1-2-form": "1.2 Application form",
    "m1-3-pi": "1.3 Product information",
    "m1-3-1-spc": "1.3.1 Summary of product characteristics",
    "m1-3-2-label": "1.3.2 Labeling",
    "m1-3-3-pil": "1.3.3 Patient information leaflet",
    "m1-3-4-mockup": "1.3.4 Artwork (mock-ups)",
    "m1-3-5-samples": "1.3.5 Samples",
    "m1-4-expert": "1.4 Information on the experts",
    "m1-4-1-quality": "1.4.1 Quality",
    "m1-4-2-non-clinical": "1.4.2 Non-clinical",
    "m1-4-3-clinical": "1.4.3 Clinical",
    "m1-5-environrisk": "1.5 Environmental risk assessment",
    "m1-5-1-non-gmo": "1.5.1 Non-GMO",
    "m1-5-2-gmo": "1.5.2 GMO",
    "m1-6-pharmacovigilance": "1.6 Pharmacovigilance",
    "m1-6-1-pharmacovigilance-system": "1.6.1 Pharmacovigilance system",
    "m1-6-2-risk-management-system": "1.6.2 Risk management plan",
    "m1-7-certificates": "1.7 Certificates and documents",
    "m1-7-1-gmp": "1.7.1 GMP certificate",
    "m1-7-2-cpp": "1.7.2 CPP or free-sale certificate",
    "m1-7-3-analysis-substance": "1.7.3 Certificate of analysis – drug substance / finished product",
    "m1-7-4-analysis-excipients": "1.7.4 Certificate of analysis – excipients",
    "m1-7-5-alcohol-content": "1.7.5 Alcohol-content declaration",
    "m1-7-6-pork-content": "1.7.6 Pork-content declaration",
    "m1-7-7-certificate-tse": "1.7.7 Certificate of suitability for TSE",
    "m1-7-8-diluent-coloring-agents": "1.7.8 Diluents and colouring agents",
    "m1-7-9-patent-information": "1.7.9 Patent information",
    "m1-7-10-letter-access-dmf": "1.7.10 Letter of access to the DMF",
    "m1-8-pricing": "1.8 Pricing",
    "m1-8-1-price-list": "1.8.1 Price list",
    "m1-8-2-other-document": "1.8.2 Other pricing documents",
    "m1-9-responses": "1.9 Responses to questions",
    "m1-additional-data": "Additional data",
}
LANGUAGE_NAMES = {"ar": "Arabic", "en": "English"}

_REPEATABLE = {"atc": "atc_codes", "invented-name": "invented_names", "inn": "inns", "related-sequence": "related_sequences"}
_TYPED = {"submission": "submission_type", "submission-unit": "submission_unit", "procedure": "procedure"}
_TEXT = {"applicant": "applicant", "sequence": "sequence", "submission-description": "description"}


def parse_envelopes(tree) -> list[dict]:
    """Every ``envelope`` in the regional XML as a plain dict (stored on the sequence as JSON)."""
    envelopes = []
    for element in tree.getroot().iter():
        if local_name(element) != "envelope":
            continue
        envelope = {"country": element.get("country", ""), "line": element.sourceline,
                    "application_numbers": [], **{key: [] for key in _REPEATABLE.values()}}
        for child in element:
            name = local_name(child)
            text = (child.text or "").strip()
            if name == "agency":
                envelope["agency"] = child.get("code", "")
            elif name == "application":
                envelope["application_numbers"] = [
                    (n.text or "").strip() for n in child if local_name(n) == "number" and (n.text or "").strip()
                ]
            elif name in _TYPED:
                envelope[_TYPED[name]] = child.get("type", "")
            elif name in _REPEATABLE:
                if text:
                    envelope[_REPEATABLE[name]].append(text)
            elif name in _TEXT:
                envelope[_TEXT[name]] = text
        envelopes.append(envelope)
    return envelopes


def select_envelope(envelopes: list[dict], country: str) -> dict | None:
    """The envelope addressed to ``country``, else the one for all GCC countries."""
    for wanted in (country, "common"):
        for envelope in envelopes:
            if envelope["country"] == wanted:
                return envelope
    return None


def _for_country(leaf, section, country) -> bool:
    """A leaf counts for ``country`` unless a closer specific/pi-doc names another country."""
    for ancestor in leaf.iterancestors():
        if ancestor is section:
            return True
        if local_name(ancestor) in ("specific", "pi-doc"):
            return ancestor.get("country") in (country, "common")
    return True


def section_documents(tree, element_name: str, country: str) -> list:
    """Leaves (not deletions) under ``element_name`` that apply to ``country``."""
    leaves = []
    for section in tree.getroot().iter():
        if local_name(section) != element_name:
            continue
        leaves += [
            leaf for leaf in section.iter()
            if local_name(leaf) == "leaf" and leaf.get("operation") != "delete" and _for_country(leaf, section, country)
        ]
    return leaves


def leaflet_languages(tree, country: str) -> set[str]:
    """Languages of the patient leaflets (1.3.3) that hold a document for ``country``."""
    languages = set()
    for pi_doc in tree.getroot().iter():
        if local_name(pi_doc) != "pi-doc" or pi_doc.get("type") != "pil":
            continue
        if pi_doc.get("country") not in (country, "common"):
            continue
        if any(local_name(leaf) == "leaf" and leaf.get("operation") != "delete" for leaf in pi_doc.iter()):
            languages.add(pi_doc.get("{http://www.w3.org/XML/1998/namespace}lang", ""))
    return languages
