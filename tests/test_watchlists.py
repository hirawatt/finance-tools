"""Tests for utils.watchlists (the curated lists in ``indices/``)."""

from __future__ import annotations

from utils.watchlists import read_watchlists, watchlist_stamp


def _write(directory, name, text):
    (directory / name).write_text(text)


def test_reads_every_row_not_just_the_first(tmp_path):
    _write(tmp_path, "ac.csv", "VOLTAS,HAVELLS\nBLUESTARCO\n")

    assert read_watchlists(tmp_path) == {"ac": ("VOLTAS", "HAVELLS", "BLUESTARCO")}


def test_expands_a_reference_to_another_watchlist(tmp_path):
    _write(tmp_path, "ac.csv", "VOLTAS,HAVELLS\n")
    _write(tmp_path, "iAirline.csv", "INDIGO\n")
    _write(tmp_path, "all.csv", "ac,iAirline\n")

    assert read_watchlists(tmp_path)["all"] == ("VOLTAS", "HAVELLS", "INDIGO")


def test_reference_cycles_are_ignored(tmp_path):
    _write(tmp_path, "a.csv", "AAA,b\n")
    _write(tmp_path, "b.csv", "BBB,a\n")

    resolved = read_watchlists(tmp_path)

    assert resolved["a"] == ("AAA", "BBB")
    assert resolved["b"] == ("BBB", "AAA")


def test_empty_watchlist_stays_empty(tmp_path):
    _write(tmp_path, "empty.csv", "")

    assert read_watchlists(tmp_path) == {"empty": ()}


def test_symbols_are_uppercased_and_deduplicated(tmp_path):
    _write(tmp_path, "a.csv", "polycab, HFCL\nPOLYCAB\n")

    assert read_watchlists(tmp_path)["a"] == ("POLYCAB", "HFCL")


def test_stamp_is_zero_for_a_directory_with_no_lists(tmp_path):
    assert watchlist_stamp(tmp_path) == 0.0


def test_stamp_moves_when_a_watchlist_is_edited(tmp_path):
    import os

    _write(tmp_path, "a.csv", "AAA\n")
    before = watchlist_stamp(tmp_path)

    _write(tmp_path, "a.csv", "BBB\n")
    os.utime(tmp_path / "a.csv", (before + 60, before + 60))

    # Cached readers key on this value, so an edit has to change it.
    assert watchlist_stamp(tmp_path) > before
