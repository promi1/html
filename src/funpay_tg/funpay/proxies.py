"""Proxy validation, rotation, and httpx-compatible transport selection."""

from __future__ import annotations

import itertools
import logging
import re
import threading
from collections.abc import Iterable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_VALID_SCHEMES = {"http", "https", "socks5", "socks4", "socks5h"}
_PROXY_RE = re.compile(
    r"^(?P<scheme>https?|socks5h?|socks4)://"
    r"(?:(?P<user>[^:@\s]+):(?P<pwd>[^@\s]*)@)?"
    r"(?P<host>[^:/\s]+):(?P<port>\d{1,5})$"
)


def normalise_proxy(raw: str) -> str:
    """Validate and normalise a proxy URL.

    Accepts ``host:port`` (defaults to http) or ``scheme://[user:pass@]host:port``.
    Returns a canonical URL string. Raises ``ValueError`` on malformed input.
    """
    raw = raw.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in _VALID_SCHEMES:
        raise ValueError(f"Unsupported proxy scheme: {parsed.scheme!r}")
    if not parsed.hostname or not parsed.port:
        raise ValueError("Proxy must include host and port")
    if not _PROXY_RE.match(raw):
        # Best-effort sanity check (urlparse is permissive); only warn.
        logger.debug("Proxy %s did not match strict regex; accepting via urlparse", raw)
    return raw


def build_async_client(
    proxy: str | None,
    *,
    user_agent: str,
    timeout: float = 25.0,
) -> httpx.AsyncClient:
    """Build a configured ``httpx.AsyncClient``.

    Uses ``httpx_socks.AsyncProxyTransport`` when a SOCKS proxy is given so we
    can support residential SOCKS proxies seamlessly.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "ru,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    if proxy:
        scheme = urlparse(proxy).scheme.lower()
        if scheme.startswith("socks"):
            from httpx_socks import AsyncProxyTransport  # imported lazily

            transport = AsyncProxyTransport.from_url(proxy)
            return httpx.AsyncClient(
                transport=transport,
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
                http2=True,
            )
        return httpx.AsyncClient(
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            http2=True,
        )

    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=False,
        http2=True,
    )


class ProxyPool:
    """Thread-safe round-robin pool of proxy URLs."""

    def __init__(self, proxies: Iterable[str] | None = None):
        self._proxies: list[str] = list(proxies or [])
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None
        self._lock = threading.Lock()

    def replace(self, proxies: Iterable[str]) -> None:
        with self._lock:
            self._proxies = list(proxies)
            self._cycle = itertools.cycle(self._proxies) if self._proxies else None

    def __len__(self) -> int:
        return len(self._proxies)

    @property
    def is_empty(self) -> bool:
        return not self._proxies

    def next(self) -> str | None:
        with self._lock:
            if not self._cycle:
                return None
            return next(self._cycle)
