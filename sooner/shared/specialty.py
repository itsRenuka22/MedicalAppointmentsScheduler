"""Specialty names: the LLM may say 'dermatologist'; clinics advertise 'dermatology'."""
SPECIALTY_ALIASES = {"dermatologist": "dermatology", "skin": "dermatology",
                     "primary care": "general", "primary": "general", "gp": "general",
                     "dentist": "dental", "dentistry": "dental"}


def normalize_specialty(value: str) -> str:
    v = str(value).strip().lower()
    return SPECIALTY_ALIASES.get(v, v)
