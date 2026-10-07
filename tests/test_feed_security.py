import pytest

from src.collectors.json_feed import validate_feed_url
from src.config import settings


def test_feed_url_requires_https_and_an_explicit_host_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "authorized_source_hosts", "partner.example,*.feeds.example")
    assert validate_feed_url("https://partner.example/catalog.json") == "partner.example"
    assert validate_feed_url("https://eu.feeds.example/catalog.json") == "eu.feeds.example"
    with pytest.raises(ValueError, match="HTTPS"):
        validate_feed_url("http://partner.example/catalog.json")
    with pytest.raises(ValueError, match="AUTHORIZED_SOURCE_HOSTS"):
        validate_feed_url("https://unknown.example/catalog.json")


def test_feed_url_rejects_embedded_credentials_and_sensitive_query(monkeypatch):
    monkeypatch.setattr(settings, "authorized_source_hosts", "partner.example")
    with pytest.raises(ValueError, match="credentials"):
        validate_feed_url("https://user:pass@partner.example/catalog.json")
    with pytest.raises(ValueError, match="credentials"):
        validate_feed_url("https://partner.example/catalog.json?api_key=secret")
