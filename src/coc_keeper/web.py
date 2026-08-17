# -*- coding: utf-8 -*-
"""本地 WebUI 与 JSON API。"""
from __future__ import annotations

import os
import random
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent.agent import KeeperAgent
from .agent.prompts import KP_SYSTEM_PROMPT
from .agent.state import Session
from .character import (
    CharacterSheet, allocate_occupation_points, allocate_skill_points,
    base_skill_values, generate_character_candidates,
)
from .character_store import CharacterStore
from .config import PROJECT_ROOT, Settings
from .game_store import GameRecord, GameStore, TranscriptEntry
from .module_store import ModuleStore
from .modules import ModuleRuntime
from .occupations import (
    get_occupation, interest_point_budget, list_occupations,
)


class DraftRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    age: int = Field(default=30, ge=15, le=90)


class CharacterCreateRequest(BaseModel):
    draft_id: str
    candidate_index: int = Field(ge=0, le=4)
    occupation_id: int
    occupation_skills: list[str]
    occupation_points: dict[str, int] = Field(default_factory=dict)
    interest_points: dict[str, int] = Field(default_factory=dict)


class SkillUpdateRequest(BaseModel):
    occupation_skills: list[str] = Field(default_factory=list)
    occupation_points: dict[str, int] = Field(default_factory=dict)
    interest_points: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] | None = None


class ModulePathRequest(BaseModel):
    path: str
    title: str | None = None


class GameCreateRequest(BaseModel):
    title: str = Field(default="新战役", max_length=80)
    character_id: str
    module_id: str


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class WebService:
    def __init__(self, data_root: str | Path | None = None):
        self.data_root = Path(data_root or os.environ.get("COC_KEEPER_DATA_DIR", PROJECT_ROOT / "data"))
        self.characters = CharacterStore(self.data_root / "characters")
        self.modules = ModuleStore(self.data_root / "modules")
        self.games = GameStore(self.data_root / "campaigns")
        self.drafts: dict[str, list[CharacterSheet]] = {}
        self._locks: dict[str, threading.Lock] = {}

    def lock(self, game_id: str) -> threading.Lock:
        self._locks.setdefault(game_id, threading.Lock())
        return self._locks[game_id]

    @staticmethod
    def character_payload(record) -> dict[str, Any]:
        return record.to_dict()

    @staticmethod
    def game_payload(record: GameRecord, *, include_transcript: bool = True) -> dict[str, Any]:
        payload = {
            "id": record.id, "title": record.title,
            "character_id": record.character_id, "module_id": record.module_id,
            "updated_at": record.updated_at,
            "character": record.session.investigator.to_dict(),
            "module": record.session.module.status(player_safe=True) if record.session.module else None,
        }
        if include_transcript:
            payload["transcript"] = [entry.__dict__ for entry in record.transcript]
        return payload


service = WebService()
app = FastAPI(title="CoC Keeper", version="1.2.0")
static_root = Path(__file__).resolve().parent / "web_static"
app.mount("/assets", StaticFiles(directory=static_root), name="assets")


@app.exception_handler(FileNotFoundError)
async def not_found_handler(_, exc: FileNotFoundError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/")
def index():
    return FileResponse(static_root / "index.html")


@app.get("/api/status")
def status():
    settings = Settings()
    return {
        "configured": settings.is_configured,
        "model": settings.model,
        "context_window": settings.context_window,
        "provider": "DeepSeek" if "deepseek" in settings.base_url.lower() else settings.base_url,
    }


@app.get("/api/characters")
def list_characters():
    return [service.character_payload(record) for record in service.characters.list()]


@app.get("/api/occupations")
def occupations():
    return [occupation.to_dict() for occupation in list_occupations()]


@app.post("/api/character-drafts")
def create_character_draft(request: DraftRequest):
    draft_id = uuid.uuid4().hex
    candidates = generate_character_candidates(request.name.strip(), request.age, count=5, rng=random.Random())
    service.drafts[draft_id] = candidates
    return {
        "draft_id": draft_id,
        "candidates": [
            {
                "index": index, "sheet": sheet.to_dict(),
                "interest_point_budget": interest_point_budget(sheet.attributes),
                "base_skills": base_skill_values(sheet.attributes),
            }
            for index, sheet in enumerate(candidates)
        ],
    }


@app.post("/api/characters")
def save_character(request: CharacterCreateRequest):
    candidates = service.drafts.get(request.draft_id)
    if candidates is None:
        raise HTTPException(status_code=404, detail="建卡候选已过期，请重新生成")
    sheet = CharacterSheet.from_dict(candidates[request.candidate_index].to_dict())
    allocate_occupation_points(
        sheet, request.occupation_id, request.occupation_skills,
        request.occupation_points, request.interest_points,
    )
    record = service.characters.create(sheet)
    service.drafts.pop(request.draft_id, None)
    return service.character_payload(record)


@app.put("/api/characters/{character_id}/skills")
def update_character_skills(character_id: str, request: SkillUpdateRequest):
    record = service.characters.get(character_id)
    if record.sheet.occupation_id is None:
        if request.skills is None:
            raise HTTPException(status_code=400, detail="旧版角色卡需要提交 skills 字段")
        allocate_skill_points(record.sheet, request.skills)
    else:
        allocate_occupation_points(
            record.sheet, record.sheet.occupation_id,
            request.occupation_skills or record.sheet.occupation_skills,
            request.occupation_points, request.interest_points,
            occupation_skill_cap=record.sheet.occupation_skill_cap,
            non_occupation_skill_cap=record.sheet.non_occupation_skill_cap,
        )
    return service.character_payload(service.characters.save(character_id, record.sheet))


@app.get("/api/character-drafts/{draft_id}/candidates/{candidate_index}/occupations/{occupation_id}")
def occupation_preview(draft_id: str, candidate_index: int, occupation_id: int):
    candidates = service.drafts.get(draft_id)
    if candidates is None:
        raise HTTPException(status_code=404, detail="建卡候选已过期，请重新生成")
    if not 0 <= candidate_index < len(candidates):
        raise HTTPException(status_code=400, detail="属性候选序号无效")
    sheet = candidates[candidate_index]
    occupation = get_occupation(occupation_id)
    payload = occupation.to_dict(sheet.attributes)
    payload["interest_point_budget"] = interest_point_budget(sheet.attributes)
    payload["base_skills"] = base_skill_values(sheet.attributes)
    return payload


@app.get("/api/modules")
def list_modules():
    return [record.summary() for record in service.modules.list()]


@app.post("/api/modules/path")
def import_module_path(request: ModulePathRequest):
    return service.modules.import_pdf(request.path, title=request.title).summary()


@app.post("/api/modules/upload")
async def upload_module(file: UploadFile = File(...), title: str | None = Form(default=None)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请选择 PDF 模组")
    content = await file.read(64 * 1024 * 1024 + 1)
    if len(content) > 64 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF 不能超过 64 MB")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=service.data_root) as temporary:
        temporary.write(content)
        temp_path = Path(temporary.name)
    try:
        return service.modules.import_pdf(temp_path, title=title or Path(file.filename).stem).summary()
    finally:
        temp_path.unlink(missing_ok=True)


@app.get("/api/games")
def list_games():
    return [service.game_payload(record, include_transcript=False) for record in service.games.list()]


@app.post("/api/games")
def create_game(request: GameCreateRequest):
    character = service.characters.get(request.character_id)
    module = service.modules.get(request.module_id)
    sheet = CharacterSheet.from_dict(character.sheet.to_dict())
    session = Session(
        investigator=sheet, module=ModuleRuntime(module.module),
        character_id=character.id, module_id=module.id,
    )
    record = service.games.create(request.title, character.id, module.id, session)
    return service.game_payload(record)


@app.get("/api/games/{game_id}")
def get_game(game_id: str):
    return service.game_payload(service.games.get(game_id))


@app.post("/api/games/{game_id}/messages")
def send_message(game_id: str, request: MessageRequest):
    with service.lock(game_id):
        record = service.games.get(game_id)
        relevant = record.relevant_history(request.content)
        prompt = KP_SYSTEM_PROMPT
        if relevant:
            prompt += "\n\n## 与当前行动相关的已发生战役记录\n" + "\n".join(f"- {item}" for item in relevant)
        settings = Settings()
        if not settings.is_configured:
            raise HTTPException(status_code=503, detail="尚未配置 DeepSeek API")
        agent = KeeperAgent(record.session, settings, system_prompt=prompt)
        agent.memory.restore(record.memory)
        try:
            reply = agent.respond(request.content)
        except Exception as exc:  # noqa: BLE001 - 转换为前端可处理的网关错误
            raise HTTPException(status_code=502, detail=f"模型调用失败: {type(exc).__name__}: {exc}") from exc
        record.transcript.extend([
            TranscriptEntry("user", request.content), TranscriptEntry("assistant", reply),
        ])
        record.memory = agent.memory.snapshot()
        service.games.save(record)
        service.characters.save(record.character_id, record.session.investigator)
        return {
            "reply": reply,
            "game": service.game_payload(record),
            "trace": agent.tracer.summary(),
        }


def main() -> None:
    host = os.environ.get("COC_KEEPER_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("COC_KEEPER_WEB_PORT", "8765"))
    uvicorn.run("coc_keeper.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
