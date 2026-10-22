# -*- coding: utf-8 -*-
import pymupdf
import time
from fastapi.testclient import TestClient
from types import SimpleNamespace

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
    index_response = client.get("/")
    assert index_response.status_code == 200
    assert index_response.headers["cache-control"] == "no-store"

    draft_response = client.post("/api/character-drafts", json={"name": "周晴", "age": 27})
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert len(draft["candidates"]) == 5
    candidate = draft["candidates"][0]
    occupations = client.get("/api/occupations").json()
    accountant = next(item for item in occupations if item["id"] == 2)
    selected_skills = list(accountant["fixed_skills"])
    extras = [name for name in candidate["base_skills"] if name not in selected_skills and name != "克苏鲁神话"]
    selected_skills.extend(extras[:accountant["free_choice_count"]])
    character_response = client.post("/api/characters", json={
        "draft_id": draft["draft_id"], "candidate_index": 0,
        "occupation_id": accountant["id"],
        "occupation_skills": selected_skills,
        "occupation_points": {"信用评级": accountant["credit_min"]},
        "interest_points": {},
    })
    assert character_response.status_code == 200
    character = character_response.json()
    assert character["permanent"] is True
    assert character["sheet"]["occupation"]["name"] == accountant["name"]
    assert character["occupation_point_budget"] == candidate["sheet"]["attributes"]["EDU"] * 4

    module_response = client.post(
        "/api/modules/upload",
        files={"file": ("test.pdf", make_pdf(), "application/pdf")},
        data={"title": "测试模组"},
    )
    assert module_response.status_code == 200
    module = module_response.json()
    assert "sections" not in module

    detail_response = client.get(f"/api/modules/{module['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["source_pdf_available"] is True
    assert detail["module"]["version"] == 2
    assert detail["module"]["source_name"] == "test.pdf"
    assert detail["module"]["source_chunks"]
    assert detail["module"]["scenes"]
    assert detail["module"]["story"]["nodes"]
    detail["module"]["title"] = "修订后的测试模组"
    detail["module"]["scenes"][0]["public_title"] = "旧宅门前"
    update_response = client.put(f"/api/modules/{module['id']}", json=detail["module"])
    assert update_response.status_code == 200
    assert update_response.json()["module"]["title"] == "修订后的测试模组"

    game_response = client.post("/api/games", json={
        "title": "测试战役", "character_id": character["id"], "module_id": module["id"],
    })
    assert game_response.status_code == 200
    game = game_response.json()
    assert game["character_id"] == character["id"]
    assert game["module_id"] == module["id"]
    assert game["character"]["name"] == "周晴"
    assert game["module"]["module"] == "修订后的测试模组"
    assert "scene" not in game["module"]
    assert "progress" not in game["module"]

    assert client.delete(f"/api/characters/{character['id']}").status_code == 409
    assert client.delete(f"/api/modules/{module['id']}").status_code == 409

    delete_response = client.delete(f"/api/games/{game['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert client.get(f"/api/games/{game['id']}").status_code == 404
    assert client.delete(f"/api/characters/{character['id']}").json()["deleted"] is True
    assert client.delete(f"/api/modules/{module['id']}").json()["deleted"] is True
    assert client.get("/api/characters").json() == []
    assert client.get("/api/modules").json() == []


def test_web_status_declares_context_window(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "service", web.WebService(tmp_path / "data"))
    client = TestClient(web.app)
    payload = client.get("/api/status").json()
    assert payload["context_window"] == 1_000_000


def test_web_can_run_deep_module_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "service", web.WebService(tmp_path / "data"))
    client = TestClient(web.app)
    module = client.post(
        "/api/modules/upload",
        files={"file": ("test.pdf", make_pdf(), "application/pdf")},
        data={"title": "待分析模组"},
    ).json()

    class StubAnalyzer:
        def __init__(self, _client, **_kwargs):
            pass

        def analyze(self, value):
            value.analysis = {"mode": "llm", "status": "complete"}
            return value

    monkeypatch.setattr(web, "Settings", lambda: SimpleNamespace(is_configured=True))
    monkeypatch.setattr(web, "LLMClient", lambda _settings: object())
    monkeypatch.setattr(web, "LLMModuleAnalyzer", StubAnalyzer)
    response = client.post(f"/api/modules/{module['id']}/analyze")
    assert response.status_code == 202
    for _ in range(100):
        status = client.get(f"/api/modules/{module['id']}/analysis").json()
        if status["status"] != "running":
            break
        time.sleep(0.01)
    assert status["status"] == "completed"
    detail = client.get(f"/api/modules/{module['id']}").json()
    assert detail["module"]["analysis"]["status"] == "complete"


def test_web_can_run_grok_visual_cross_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "service", web.WebService(tmp_path / "data"))
    client = TestClient(web.app)
    module = client.post(
        "/api/modules/upload",
        files={"file": ("vision.pdf", make_pdf(), "application/pdf")},
        data={"title": "视觉模组"},
    ).json()

    class VisionResult:
        pages = ["Corrected visual page with actor statistics and clues."]

        @staticmethod
        def metadata():
            return {"provider": "Grok", "model": "grok-4.5", "status": "complete"}

    class StubVision:
        def __init__(self, _client, **_kwargs):
            pass

        def extract(self, _path):
            return VisionResult()

    class StubAnalyzer:
        def __init__(self, _client, **_kwargs):
            pass

        def analyze(self, value):
            value.analysis = {**value.analysis, "mode": "llm", "status": "complete"}
            return value

    monkeypatch.setattr(web, "Settings", lambda: SimpleNamespace(is_configured=True))
    monkeypatch.setattr(web, "GrokVisionSettings", lambda: SimpleNamespace(
        is_configured=True, model="grok-4.5",
    ))
    monkeypatch.setattr(web, "LLMClient", lambda _settings: object())
    monkeypatch.setattr(web, "GrokPDFVisionExtractor", StubVision)
    monkeypatch.setattr(web, "LLMModuleAnalyzer", StubAnalyzer)
    response = client.post(f"/api/modules/{module['id']}/analyze?use_vision=true")
    assert response.status_code == 202
    for _ in range(100):
        status = client.get(f"/api/modules/{module['id']}/analysis").json()
        if status["status"] != "running":
            break
        time.sleep(0.01)
    assert status["status"] == "completed"
    detail = client.get(f"/api/modules/{module['id']}").json()
    chunk = detail["module"]["source_chunks"][0]
    assert chunk["extraction_method"] == "hybrid-vision"
    assert "Corrected visual page" in chunk["text"]
    assert chunk["raw_text"]


def test_web_attribute_labels_are_bilingual():
    client = TestClient(web.app)
    page = client.get("/").text
    assert "/assets/app.js?v=2.1.0" in page
    assert "/assets/styles.css?v=2.1.0" in page
    assert 'id="sidebar-toggle"' in page
    script = client.get("/assets/app.js")
    assert script.status_code == 200
    assert 'APP: "外貌"' in script.text
    assert 'return `${ATTRIBUTE_LABELS[name] || name} | ${name}`;' in script.text
    assert "属性总和（含幸运）" in script.text
    assert "属性总和（不含幸运）" in script.text
    assert 'id="investigator-toggle"' in script.text
    assert "game.module?.progress" not in script.text
    assert "item.sections" not in script.text
    assert 'class="icon-button danger delete-game"' in script.text
    assert 'class="icon-button danger delete-character"' in script.text
    assert 'class="icon-button danger delete-module"' in script.text
    assert "检查 / 编辑" in script.text
    assert "角色与怪物" in script.text
    assert "地点与场景" in script.text
    assert "故事线" in script.text
    assert "文本重新分析" in script.text
    assert "Grok 视觉交叉分析" in script.text
    assert 'method: "DELETE"' in script.text
