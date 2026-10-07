import re
import unicodedata
from difflib import SequenceMatcher


def normalize_token(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def canonical_product_key(name: str, brand: str | None = None, model: str | None = None) -> str:
    """Create a stable identity key while preserving meaningful model numbers."""
    brand_key = normalize_token(brand)
    model_key = normalize_token(model)
    name_key = normalize_token(name)
    identity = model_key or name_key
    key = " ".join(part for part in (brand_key, identity) if part)
    return key[:320]


def identity_similarity(
    left_name: str,
    left_brand: str | None,
    left_model: str | None,
    right_name: str,
    right_brand: str | None,
    right_model: str | None,
) -> float:
    """Conservative fuzzy score for suggestions; never merge across different brands."""
    left_brand_key, right_brand_key = normalize_token(left_brand), normalize_token(right_brand)
    if left_brand_key and right_brand_key and left_brand_key != right_brand_key:
        return 0.0
    left_identity = normalize_token(left_model) or normalize_token(left_name)
    right_identity = normalize_token(right_model) or normalize_token(right_name)
    if not left_identity or not right_identity:
        return 0.0
    return SequenceMatcher(None, left_identity, right_identity).ratio()
