# -*- coding: utf-8 -*-
import pytest

from coc_keeper.storage import JsonRecordRepository


def _repo(tmp_path):
    return JsonRecordRepository(
        tmp_path / "records",
        id_pattern=r"[0-9a-f]{32}",
        decode=lambda data: dict(data),
        encode=lambda value: dict(value),
        label="记录",
        sort_key=lambda value: value["updated_at"],
    )


def test_repository_put_get_list_delete(tmp_path):
    repo = _repo(tmp_path)
    record_id = "a" * 32
    repo.put(record_id, {"id": record_id, "updated_at": "2026-01-01"})
    assert repo.get(record_id)["id"] == record_id
    assert [item["id"] for item in repo.list()] == [record_id]
    repo.delete(record_id)
    with pytest.raises(FileNotFoundError):
        repo.get(record_id)


def test_repository_rejects_bad_id_and_skips_broken_json(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        repo.get("not-an-id")
    (tmp_path / "records" / "broken.json").write_text("{", encoding="utf-8")
    assert repo.list() == []
