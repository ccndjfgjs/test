from src.services.normalization import canonical_product_key, identity_similarity, normalize_token


def test_normalize_unicode_and_punctuation():
    assert normalize_token("  RTX 4070-SUPER ") == "rtx 4070 super"
    assert normalize_token("Ёлка") == "ёлка"


def test_canonical_identity_prefers_model_number():
    assert canonical_product_key("A long marketplace title", "NVIDIA", "RTX 4070 SUPER") == "nvidia rtx 4070 super"


def test_similarity_is_brand_aware():
    assert identity_similarity("RTX 4070", "NVIDIA", "RTX 4070", "GeForce RTX 4070", "NVIDIA", "RTX 4070") > 0.9
    assert identity_similarity("RTX 4070", "NVIDIA", "RTX 4070", "RTX 4070", "AMD", "RTX 4070") == 0
