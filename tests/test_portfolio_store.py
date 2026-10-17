"""Tests for the privacy-first portfolio store."""

import sys
import types

import pandas as pd
import pytest

from utils import portfolio_store


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Symbol": ["RELIANCE", "HFCL"],
            "Total Quantity": [10.0, 100.0],
            "Invested Value": [25005.0, 8000.0],
            "Current Value": [29000.0, 9000.0],
        }
    )


class TestPaths:
    def test_a_path_can_never_escape_the_root(self, tmp_path):
        root = tmp_path.resolve()
        for name in ("../etc/passwd", "/etc/passwd", "My Client", "a/b"):
            path = portfolio_store.client_path(name, tmp_path)
            assert path is None or root in path.parents

    def test_blank_names_have_no_path(self, tmp_path):
        assert portfolio_store.client_path("", tmp_path) is None
        assert portfolio_store.client_path("..", tmp_path) is None

    def test_client_path_sits_under_the_root(self, tmp_path):
        path = portfolio_store.client_path("My Client", tmp_path)
        assert path is not None
        assert path.parent == tmp_path.resolve()
        assert path.name == "My-Client.csv"


class TestLocalStore:
    def test_round_trip(self, tmp_path):
        store = portfolio_store.LocalStore(tmp_path)
        store.save("Sharma", frame())
        assert store.list() == ["Sharma"]
        loaded = store.load("Sharma")
        assert loaded is not None
        assert loaded["Symbol"].tolist() == ["RELIANCE", "HFCL"]

    def test_load_missing_is_none(self, tmp_path):
        assert portfolio_store.LocalStore(tmp_path).load("Nobody") is None

    def test_delete(self, tmp_path):
        store = portfolio_store.LocalStore(tmp_path)
        store.save("Sharma", frame())
        store.delete("Sharma")
        assert store.list() == []

    def test_save_without_a_name_raises(self, tmp_path):
        with pytest.raises(ValueError):
            portfolio_store.LocalStore(tmp_path).save("", frame())


class TestActivePortfolio:
    def test_set_and_get_with_a_stub_session(self, monkeypatch):
        fake = types.SimpleNamespace(session_state={})
        monkeypatch.setitem(sys.modules, "streamlit", fake)

        assert portfolio_store.get_active() is None
        portfolio_store.set_active(frame(), label="Sharma")
        active = portfolio_store.get_active()
        assert active is not None and len(active) == 2
        assert portfolio_store.active_label() == "Sharma"

        portfolio_store.clear_active()
        assert portfolio_store.get_active() is None


if __name__ == "__main__":
    pytest.main([__file__])
