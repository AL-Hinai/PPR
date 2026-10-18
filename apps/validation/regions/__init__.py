"""Regional Module 1 profiles. ``ECTD_REGION`` selects one; each knows its regional XML, DTD and envelope."""
from django.core.exceptions import ImproperlyConfigured

from .base import RegionProfile
from .gcc import GCC

PROFILES = {GCC.code: GCC}


def get_profile(code: str) -> RegionProfile:
    try:
        return PROFILES[code]
    except KeyError:
        raise ImproperlyConfigured(f"Unknown ECTD_REGION '{code}'. Known regions: {', '.join(PROFILES)}") from None
