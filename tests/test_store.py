"""Scripts SQLite store — CRUD, name uniqueness, error mapping."""
import pytest

import config
from api import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")


def test_create_list_get_roundtrip():
    created = store.create_script("EMA Cross", "strategy(\"t\")")
    assert created["id"] == 1
    assert created["name"] == "EMA Cross"
    assert created["source"] == "strategy(\"t\")"
    assert created["created_at"] == created["updated_at"]

    metas = store.list_scripts()
    assert len(metas) == 1
    assert metas[0]["name"] == "EMA Cross"
    assert "source" not in metas[0]

    fetched = store.get_script(created["id"])
    assert fetched == created


def test_update_source_bumps_updated_at():
    row = store.create_script("s", "v1")
    updated = store.update_script(row["id"], source="v2")
    assert updated["source"] == "v2"
    assert updated["updated_at"] > row["updated_at"]
    assert updated["created_at"] == row["created_at"]


def test_rename():
    row = store.create_script("old", "src")
    updated = store.update_script(row["id"], name="new")
    assert updated["name"] == "new"
    assert store.get_script(row["id"])["name"] == "new"


def test_duplicate_name_rejected_case_insensitive():
    store.create_script("Foo", "a")
    with pytest.raises(ValueError, match="already exists"):
        store.create_script("foo", "b")


def test_rename_to_existing_name_rejected():
    store.create_script("a", "1")
    row = store.create_script("b", "2")
    with pytest.raises(ValueError, match="already exists"):
        store.update_script(row["id"], name="A")


def test_empty_name_rejected():
    with pytest.raises(ValueError, match="empty"):
        store.create_script("   ", "src")
    row = store.create_script("ok", "src")
    with pytest.raises(ValueError, match="empty"):
        store.update_script(row["id"], name="")


def test_delete():
    row = store.create_script("gone", "src")
    store.delete_script(row["id"])
    assert store.list_scripts() == []


def test_missing_id_raises_keyerror():
    with pytest.raises(KeyError):
        store.get_script(999)
    with pytest.raises(KeyError):
        store.update_script(999, source="x")
    with pytest.raises(KeyError):
        store.delete_script(999)


def test_update_nothing_returns_row():
    row = store.create_script("noop", "src")
    assert store.update_script(row["id"]) == row
