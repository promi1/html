"""Unit tests for the proxy normalisation and pool helpers."""

from __future__ import annotations

import pytest

from funpay_tg.funpay.proxies import ProxyPool, normalise_proxy


def test_normalise_proxy_adds_default_scheme() -> None:
    assert normalise_proxy("1.2.3.4:8080") == "http://1.2.3.4:8080"


def test_normalise_proxy_preserves_socks5_and_creds() -> None:
    proxy = "socks5://user:pass@host.example:1080"
    assert normalise_proxy(proxy) == proxy


def test_normalise_proxy_rejects_unknown_scheme() -> None:
    with pytest.raises(ValueError):
        normalise_proxy("ftp://1.2.3.4:21")


def test_normalise_proxy_requires_port() -> None:
    with pytest.raises(ValueError):
        normalise_proxy("http://1.2.3.4")


def test_proxy_pool_round_robin() -> None:
    pool = ProxyPool(["http://a:1", "http://b:2", "http://c:3"])
    assert pool.next() == "http://a:1"
    assert pool.next() == "http://b:2"
    assert pool.next() == "http://c:3"
    assert pool.next() == "http://a:1"


def test_proxy_pool_empty_returns_none() -> None:
    pool = ProxyPool([])
    assert pool.is_empty
    assert pool.next() is None


def test_proxy_pool_replace() -> None:
    pool = ProxyPool(["http://a:1"])
    pool.replace(["http://x:9", "http://y:8"])
    assert len(pool) == 2
    assert pool.next() == "http://x:9"
    assert pool.next() == "http://y:8"
