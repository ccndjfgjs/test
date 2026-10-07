"""Safe-by-default adapter for authorized JSON feeds.

This collector does not bypass bot checks, solve CAPTCHAs, rotate proxies, or
follow redirects. Hosts must be explicitly allowlisted by the operator.
"""

import asyncio
import ipaddress
import json
import socket
import time
from urllib.parse import parse_qsl, urlparse

import httpx

from src.api.schemas import OfferRecordIn
from src.config import settings

MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_FEED_RECORDS = 500
MIN_HOST_INTERVAL_SECONDS = 1.0
_host_locks: dict[str, asyncio.Lock] = {}
_last_request_at: dict[str, float] = {}


def _host_is_allowed(host: str) -> bool:
    host = host.casefold().rstrip(".")
    for item in settings.allowed_source_hosts:
        item = item.casefold().strip().rstrip(".")
        if item.startswith("*."):
            suffix = item[1:]
            if host.endswith(suffix) and host != suffix[1:]:
                return True
        elif host == item:
            return True
    return False


def validate_feed_url(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("Feed URL must be an HTTPS URL without embedded credentials")
    if parsed.port not in (None, 443):
        raise ValueError("Only the standard HTTPS port is permitted")
    sensitive_keys = {"api_key", "apikey", "access_token", "token", "secret", "signature", "sig", "password", "key"}
    if any(key.casefold() in sensitive_keys for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("Do not put credentials in feed URLs; implement a secured source adapter")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Use an allowlisted DNS hostname, not an IP address")
    if not _host_is_allowed(host):
        raise ValueError("Feed host is not in AUTHORIZED_SOURCE_HOSTS")
    return host


async def _enforce_host_interval(host: str) -> None:
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        delay = MIN_HOST_INTERVAL_SECONDS - (now - _last_request_at.get(host, 0.0))
        if delay > 0:
            await asyncio.sleep(delay)
        _last_request_at[host] = time.monotonic()


async def _resolve_public_host(host: str) -> None:
    """Reject private/link-local destinations before issuing a feed request."""
    loop = asyncio.get_running_loop()
    try:
        addresses = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Feed host could not be resolved") from exc
    if not addresses:
        raise ValueError("Feed host did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Feed host resolves to a non-public network address")


async def fetch_json_feed(feed_url: str) -> list[dict]:
    host = validate_feed_url(feed_url)
    await _resolve_public_host(host)
    await _enforce_host_interval(host)
    timeout = httpx.Timeout(20.0, connect=5.0)
    payload = bytearray()
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": settings.source_user_agent, "Accept": "application/json"},
    ) as client:
        async with client.stream("GET", feed_url) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("Feed redirects are disabled; configure the final HTTPS URL")
            response.raise_for_status()
            declared_length = response.headers.get("content-length")
            if declared_length and declared_length.isdigit() and int(declared_length) > MAX_FEED_BYTES:
                raise ValueError("Feed response exceeds the 5 MB limit")
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > MAX_FEED_BYTES:
                    raise ValueError("Feed response exceeds the 5 MB limit")

    try:
        body = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Feed response is not valid JSON") from exc

    raw_records = body.get("records") if isinstance(body, dict) else body
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("Feed JSON must be a non-empty array or an object with a records array")
    if len(raw_records) > MAX_FEED_RECORDS:
        raise ValueError(f"Feed may contain at most {MAX_FEED_RECORDS} records per job")
    return [OfferRecordIn.model_validate(record).model_dump(mode="json") for record in raw_records]
