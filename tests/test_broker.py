"""Checks the paper-only safety rules. These run without internet or real keys."""
import pytest

from data import broker


def test_paper_key_is_accepted():
    broker.check_paper_key("PKABC123")


@pytest.mark.parametrize("key", ["AKABC123", "ABC123", "", "pkabc"])
def test_non_paper_key_is_refused(key):
    with pytest.raises(broker.LiveKeyError):
        broker.check_paper_key(key)


def test_trading_client_is_always_paper(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKTEST")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    client = broker.trading_client()
    assert "paper-api.alpaca.markets" in client._base_url


def test_live_key_never_builds_a_client(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "AKLIVEKEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    with pytest.raises(broker.LiveKeyError):
        broker.trading_client()
