# -*- coding: utf-8 -*-
import pymupdf
from fastapi.testclient import TestClient

import coc_keeper.web as web


def make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A short scenario begins in an old house with a locked door.")
    payload = doc.tobytes()
    doc.close()
    return payload


def test_web_character_module_and_game_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "service", web.WebService(tmp_path / "data"))
    client = TestClient(web.app)
    assert client.get("/").status_code == 200

    draft_response = client.post("/api/character-drafts", json={"name": "周晴", "age": 27})
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert len(draft["candidates"]) == 5
    candidate = draft["candidates"][0]
    character_response = client.post("/api/characters", json={
        "draft_id": draft["draft_id"], "candidate_index": 0,
        "skills": candidate["base_skills"],
    })
    assert character_response.status_code == 200
    character = character_response.json()
    assert character["permanent"] is True

    module_response = client.post(
        "/api/modules/upload",
        files={"file": ("test.pdf", make_pdf(), "application/pdf")},
        data={"title": "测试模组"},
    )
    assert module_response.status_code == 200
    module = module_response.json()

    game_response = client.post("/api/games", json={
        "title": "测试战役", "character_id": character["id"], "module_id": module["id"],
    })
    assert game_response.status_code == 200
    game = game_response.json()
    assert game["character_id"] == character["id"]
    assert game["module_id"] == module["id"]
    assert game["character"]["name"] == "周晴"
    assert game["module"]["module"] == "测试模组"


def test_web_status_declares_context_window(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "service", web.WebService(tmp_path / "data"))
    client = TestClient(web.app)
    payload = client.get("/api/status").json()
    assert payload["context_window"] == 1_000_000
