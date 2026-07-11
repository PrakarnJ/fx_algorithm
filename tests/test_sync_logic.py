"""Pure sync helpers — mode resolution, from-date computation, single-flight.

No subprocess or network: the worker itself is exercised manually (see plan
verification); these tests cover the decision logic only.
"""
import threading

import pytest

import config
from api import sync
from conftest import make_bars


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # reset module state between tests
    sync._state.update(status="idle", mode=None, step=None,
                       started_at=None, finished_at=None, error=None)


def test_resolve_mode_no_marker_is_full():
    assert sync.resolve_mode("auto", None) == "full"


def test_resolve_mode_with_marker_is_incremental():
    assert sync.resolve_mode("auto", {"last_synced": "2026-01-01T00:00:00Z"}) == "incremental"


def test_resolve_mode_forced_full():
    assert sync.resolve_mode("full", {"last_synced": "2026-01-01T00:00:00Z"}) == "full"


def test_compute_from_date_full_mode():
    assert sync.compute_from_date("M15", "full") == sync.FULL_START


def test_compute_from_date_incremental_no_csv_falls_back_to_full_start():
    assert sync.compute_from_date("M15", "incremental") == sync.FULL_START


def test_compute_from_date_incremental_uses_last_bar_minus_overlap(tmp_path):
    df = make_bars(n=10, freq="D")  # last bar 2024-01-10
    df.index.name = "time"
    df.to_csv(tmp_path / config.TF_TO_FILE["M15"])
    assert sync.compute_from_date("M15", "incremental") == "2024-01-08"


def test_read_marker_roundtrip(tmp_path):
    assert sync.read_marker() is None
    (tmp_path / ".sync_meta.json").write_text('{"last_synced": "x"}')
    assert sync.read_marker() == {"last_synced": "x"}


def test_single_flight_guard(monkeypatch):
    # Stop the thread from doing anything real
    monkeypatch.setattr(threading, "Thread",
                        lambda *a, **k: type("T", (), {"start": lambda self: None})())
    first = sync.start_sync("auto")
    assert first == "full"
    assert sync.get_status()["status"] == "running"
    assert sync.start_sync("auto") is None  # already running
