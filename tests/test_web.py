# -*- coding: utf-8 -*-
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import coc_keeper.web as web
from coc_keeper.modules import KeeperModule, ModuleScene


def make_module(title="测试模组") -> KeeperModule:
    return KeeperModule(title, "test.pdf", [
        ModuleScene(
            "scene-001", "门厅", "旧宅门前", 1, 1,
            "门厅里有一把生锈钥匙。", objectives=["找到钥匙"],
        ),
    ])


def make_context(tmp_path) -> web.AppContext:
    context = web.AppContext(tmp_path / "data")
    return context


def wait_job(client, job_id):
    for _ in range(200):
        payload = client.get(f"/api/imports/{job_id}").json()
        if payload["status"] != "running":
            return payload
        time.sleep(0.01)
    return payload


def test_web_character_module_and_game_flow(tmp_path):
    context = make_context(tmp_path)
    client = TestClient(web.create_app(context))
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

    source = tmp_path / "test.pdf"
    source.write_bytes(b"%PDF-1.4\n% fake module\n")
    record = context.modules.create(make_module(), source_pdf=source)
    detail_response = client.get(f"/api/modules/{record.id}")
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
    update_response = client.put(f"/api/modules/{record.id}", json=detail["module"])
    assert update_response.status_code == 200
    assert update_response.json()["module"]["title"] == "修订后的测试模组"

    game_response = client.post("/api/games", json={
        "title": "测试战役", "character_id": character["id"], "module_id": record.id,
    })
    assert game_response.status_code == 200
    game = game_response.json()
    assert game["character_id"] == character["id"]
    assert game["module_id"] == record.id
    assert game["character"]["name"] == "周晴"
    assert game["module"]["module"] == "修订后的测试模组"
    assert "scene" not in game["module"]
    assert "progress" not in game["module"]

    assert client.delete(f"/api/characters/{character['id']}").status_code == 409
    assert client.delete(f"/api/modules/{record.id}").status_code == 409

    delete_response = client.delete(f"/api/games/{game['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert client.get(f"/api/games/{game['id']}").status_code == 404
    assert client.delete(f"/api/characters/{character['id']}").json()["deleted"] is True
    assert client.delete(f"/api/modules/{record.id}").json()["deleted"] is True
    assert client.get("/api/characters").json() == []
    assert client.get("/api/modules").json() == []


def test_web_status_declares_mineru_and_deepseek(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    monkeypatch.setattr(web, "Settings", lambda: SimpleNamespace(
        is_configured=True, model="deepseek-flash",
        context_window=1_000_000, base_url="https://api.deepseek.com",
        mineru_api_key="mineru-key", mineru_base_url="https://mineru.net",
    ))
    client = TestClient(web.create_app(context))
    payload = client.get("/api/status").json()
    assert payload["context_window"] == 1_000_000
    assert payload["mineru"]["configured"] is True
    assert payload["review"] == {
        "configured": True, "provider": "DeepSeek", "model": "deepseek-flash",
    }
    assert "vision" not in payload


def test_web_upload_runs_background_import_job(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    client = TestClient(web.create_app(context))

    class StubService:
        def import_pdf(self, source_path, *, title=None, source_name=None, remove_source=False):
            def run(report):
                report("MinerU 解析 PDF")
                record = context.modules.create(make_module(title or "上传模组"))
                return {"module_id": record.id, "module": record.summary()}
            return context.jobs.submit("module-import", run)

    context.module_service = StubService()
    response = client.post(
        "/api/modules/upload",
        files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"title": "上传模组"},
    )
    assert response.status_code == 202
    job = wait_job(client, response.json()["job_id"])
    assert job["status"] == "completed"
    assert client.get(f"/api/modules/{job['result']['module_id']}").status_code == 200


def test_web_reanalyze_uses_background_job(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    client = TestClient(web.create_app(context))
    source = tmp_path / "test.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    record = context.modules.create(make_module(), source_pdf=source)

    class StubService:
        def reanalyze(self, module_id, *, reparse=False, review=True):
            def run(report):
                report("DeepSeek 复核")
                stored = context.modules.get(module_id)
                stored.module.analysis = {"mode": "llm", "status": "complete"}
                context.modules.save(module_id, stored.module)
                return {"module_id": module_id}
            return context.jobs.submit("module-reanalyze", run)

    context.module_service = StubService()
    monkeypatch.setattr(web, "Settings", lambda: SimpleNamespace(mineru_api_key="mineru-key", is_configured=True))
    response = client.post(f"/api/modules/{record.id}/analyze?reparse=true")
    assert response.status_code == 202
    for _ in range(200):
        payload = client.get(f"/api/modules/{record.id}/analysis").json()
        if payload["status"] != "running":
            break
        time.sleep(0.01)
    assert payload["status"] == "completed"
    detail = client.get(f"/api/modules/{record.id}").json()
    assert detail["module"]["analysis"]["status"] == "complete"


def test_web_skill_catalog_api(tmp_path):
    context = make_context(tmp_path)
    client = TestClient(web.create_app(context))
    payload = client.get("/api/skills?q=取悦").json()
    assert payload["skills"][0]["canonical_name"] == "魅惑"
    detail = client.get("/api/skills/detail?name=%E8%A1%A8%E6%BC%94").json()
    assert detail["canonical_name"] == "艺术/手艺"
    assert detail["sections"]["description"]
    slash_detail = client.get("/api/skills/detail?name=%E8%89%BA%E6%9C%AF%2F%E6%89%8B%E8%89%BA").json()
    assert slash_detail["canonical_name"] == "艺术/手艺"
    categories = client.get("/api/skills").json()["categories"]
    assert "investigation" in categories and "social" in categories


def test_web_skill_all_category_matches_frontend_request(tmp_path):
    client = TestClient(web.create_app(make_context(tmp_path)))
    all_skills = client.get("/api/skills?limit=80").json()
    assert all_skills["count"] > 0
    for category in ("", "   "):
        assert client.get("/api/skills", params={"category": category, "limit": 80}).json() == all_skills
        result = client.get("/api/skills", params={"q": "侦查", "category": category}).json()
        assert result["skills"][0]["canonical_name"] == "侦查"


def test_applications_keep_separate_contexts_and_drafts(tmp_path):
    first = make_context(tmp_path / "first")
    second = make_context(tmp_path / "second")
    app_a, app_b = web.create_app(first), web.create_app(second)
    assert app_a is not app_b
    with TestClient(app_a) as a, TestClient(app_b) as b:
        draft = a.post("/api/character-drafts", json={"name": "甲"}).json()
        assert draft["draft_id"] in first.drafts
        assert draft["draft_id"] not in second.drafts
        from coc_keeper.character import CharacterSheet
        first.characters.create(CharacterSheet(name="甲"))
        assert a.get("/api/characters").json()[0]["sheet"]["name"] == "甲"
        assert b.get("/api/characters").json() == []


def make_turn_client(tmp_path, monkeypatch):
    from coc_keeper.character import CharacterSheet

    context = make_context(tmp_path)
    character = context.characters.create(CharacterSheet(name="调查员", hp=10))
    module = context.modules.create(make_module())
    client = TestClient(web.create_app(context))
    game = client.post("/api/games", json={
        "character_id": character.id, "module_id": module.id,
    }).json()
    calls = []

    class FakeAgent:
        def __init__(self, session, *args, **kwargs):
            self.session = session
            self.memory = SimpleNamespace(restore=lambda *a, **k: None, snapshot=lambda: [])
            self.tracer = SimpleNamespace(summary=lambda: {"tools": 1})

        def respond(self, text):
            calls.append(text)
            if text == "受伤":
                self.session.investigator.hp -= 3
            return "已处理：" + text

    monkeypatch.setattr(web, "KeeperAgent", FakeAgent)
    monkeypatch.setattr(web, "Settings", lambda: SimpleNamespace(
        is_configured=True, requires_reasoning_content=False,
    ))
    return context, character, module, client, game, calls


def test_old_campaign_uses_latest_permanent_character(tmp_path, monkeypatch):
    context, character, module, client, first, _ = make_turn_client(tmp_path, monkeypatch)
    second = client.post("/api/games", json={
        "character_id": character.id, "module_id": module.id,
    }).json()
    assert client.post(f"/api/games/{first['id']}/messages", json={"content": "受伤"}).status_code == 200
    latest = context.characters.get(character.id)
    latest.sheet.skills["侦查"] = 75
    context.characters.save(character.id, latest.sheet)
    response = client.post(f"/api/games/{second['id']}/messages", json={"content": "观察"})
    assert response.status_code == 200
    assert response.json()["game"]["character"]["current"]["hp"] == 7
    assert response.json()["game"]["character"]["skills"]["侦查"] == 75
    assert context.characters.get(character.id).sheet.hp == 7


def test_retried_turn_is_persistently_idempotent(tmp_path, monkeypatch):
    context, character, _, client, game, calls = make_turn_client(tmp_path, monkeypatch)
    path = f"/api/games/{game['id']}/messages"
    request = {"content": "受伤", "request_id": "turn-1"}
    first = client.post(path, json=request)
    assert first.status_code == 200
    # 应用重建后也从存档识别已经提交的请求。
    restarted = TestClient(web.create_app(web.AppContext(context.data_root)))
    repeated = restarted.post(path, json=request)
    assert repeated.status_code == 200
    assert repeated.json()["reply"] == first.json()["reply"]
    assert len(repeated.json()["game"]["transcript"]) == 2
    assert context.characters.get(character.id).sheet.hp == 7
    assert calls == ["受伤"]
    conflict = restarted.post(path, json={"content": "观察", "request_id": "turn-1"})
    assert conflict.status_code == 409
    assert calls == ["受伤"]


@pytest.mark.parametrize("failed_store", ["characters", "games"])
def test_turn_save_failure_rolls_back_both_records(tmp_path, monkeypatch, failed_store):
    context, character, _, client, game, _ = make_turn_client(tmp_path, monkeypatch)
    original_game = context.games.get(game["id"]).to_dict()
    original_character = context.characters.get(character.id).to_dict()
    store = getattr(context, failed_store)
    original_save = store.save

    def fail(*args, **kwargs):
        raise OSError("injected write failure")

    monkeypatch.setattr(store, "save", fail)
    path = f"/api/games/{game['id']}/messages"
    payload = {"content": "受伤", "request_id": "retry-after-rollback"}
    assert client.post(path, json=payload).status_code == 503
    assert context.games.get(game["id"]).to_dict() == original_game
    assert context.characters.get(character.id).to_dict() == original_character
    assert list(context.turns.journal.root.glob("*.json")) == []
    monkeypatch.setattr(store, "save", original_save)
    response = client.post(path, json=payload)
    assert response.status_code == 200
    assert response.json()["game"]["character"]["current"]["hp"] == 7
    assert len(response.json()["game"]["transcript"]) == 2


def test_first_request_reports_recovery_failure_as_unavailable(monkeypatch):
    application = web.create_app()

    def fail_init():
        raise OSError("injected startup recovery failure")

    monkeypatch.setattr(web, "AppContext", fail_init)
    response = TestClient(application).get("/api/characters")
    assert response.status_code == 503
    assert "恢复" in response.json()["detail"]


def test_character_edit_recovers_a_pending_turn_before_writing(tmp_path, monkeypatch):
    context, character, _, _, game, _ = make_turn_client(tmp_path, monkeypatch)
    before_game = context.games.get(game["id"]).to_dict()
    before_character = context.characters.get(character.id).to_dict()
    transaction_id = "c" * 32
    context.turns.journal.put(transaction_id, {
        "id": transaction_id, "state": "pending",
        "game_before": before_game, "character_before": before_character,
    })
    latest = context.characters.get(character.id)
    latest.sheet.hp = 7
    context.characters.save(character.id, latest.sheet)
    # 模拟依赖已执行、但角色锁排队期间新产生了待恢复事务。
    response = web.update_character_skills(
        character.id, web.SkillUpdateRequest(skills={"侦查": 40}), context=context,
    )
    assert response["sheet"]["current"]["hp"] == 10
    assert response["sheet"]["skills"]["侦查"] == 40
    context.turns.recover()
    assert context.characters.get(character.id).sheet.skills["侦查"] == 40


def test_web_attribute_labels_and_asset_version(tmp_path):
    context = make_context(tmp_path)
    client = TestClient(web.create_app(context))
    page = client.get("/").text
    assert "/assets/app.js?v=2.3.0" in page
    assert "/assets/styles.css?v=2.3.0" in page
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
    assert "重新解析并复核" in script.text
    assert "技能说明与判定参考" in script.text
    assert 'method: "DELETE"' in script.text
