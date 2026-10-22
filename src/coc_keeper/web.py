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
from .module_service import ModuleApplicationService
from .module_store import ModuleStore
from .modules import KeeperModule, ModuleRuntime
from .web_jobs import JobManager
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


class ModuleUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_name: str = Field(default="", max_length=260)
    actors: list[dict[str, Any]] = Field(default_factory=list)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    source_chunks: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(min_length=1)
    story: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)


class GameCreateRequest(BaseModel):
    title: str = Field(default="新战役", max_length=80)
    character_id: str
    module_id: str


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AppContext:
    def __init__(self, data_root: str | Path | None = None):
        self.data_root = Path(data_root or os.environ.get("COC_KEEPER_DATA_DIR", PROJECT_ROOT / "data"))
        self.characters = CharacterStore(self.data_root / "characters")
        self.modules = ModuleStore(self.data_root / "modules")
        self.games = GameStore(self.data_root / "campaigns")
        self.drafts: dict[str, list[CharacterSheet]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self.jobs = JobManager()
        self.module_jobs: dict[str, str] = {}
        self.module_service = ModuleApplicationService(
            self.modules, self.jobs, data_root=self.data_root,
        )

    def lock(self, game_id: str) -> threading.Lock:
        self._locks.setdefault(game_id, threading.Lock())
        return self._locks[game_id]

    @staticmethod
    def character_payload(record) -> dict[str, Any]:
        return record.to_dict()

    def module_payload(self, record) -> dict[str, Any]:
        summary = record.summary()
        payload = {key: summary[key] for key in ("id", "title", "source_name", "pages", "created_at")}
        payload["analysis_status"] = summary["analysis_status"]
        payload["warnings"] = len(record.module.analysis.get("review", {}).get("warnings", []))
        payload["source_pdf_available"] = self.modules.source_pdf_path(record.id) is not None
        return payload

    def module_detail_payload(self, record) -> dict[str, Any]:
        return {
            "id": record.id,
            "created_at": record.created_at,
            "source_pdf_available": self.modules.source_pdf_path(record.id) is not None,
            "module": record.module.to_dict(),
        }

    def referencing_games(self, *, character_id: str | None = None, module_id: str | None = None) -> list[GameRecord]:
        return [
            record for record in self.games.list()
            if (character_id is None or record.character_id == character_id)
            and (module_id is None or record.module_id == module_id)
        ]

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


app = FastAPI(title="CoC Keeper", version="2.1.0")
static_root = Path(__file__).resolve().parent / "web_static"
app.mount("/assets", StaticFiles(directory=static_root), name="assets")


def get_context() -> AppContext:
    """按需创建默认上下文；测试可通过 create_app(context) 注入临时目录。"""
    if not hasattr(app.state, "context"):
        app.state.context = AppContext()
    return app.state.context


def create_app(context: AppContext | None = None) -> FastAPI:
    app.state.context = context or AppContext()
    return app


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
    return FileResponse(static_root / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status():
    settings = Settings()
    return {
        "configured": settings.is_configured,
        "model": settings.model,
        "context_window": settings.context_window,
        "provider": "DeepSeek" if "deepseek" in settings.base_url.lower() else settings.base_url,
        "mineru": {
            "configured": bool(settings.mineru_api_key),
            "base_url": settings.mineru_base_url,
        },
        "review": {
            "configured": settings.is_configured,
            "provider": "DeepSeek",
            "model": settings.model,
        },
    }


@app.get("/api/characters")
def list_characters():
    return [get_context().character_payload(record) for record in get_context().characters.list()]


@app.get("/api/occupations")
def occupations():
    return [occupation.to_dict() for occupation in list_occupations()]


@app.post("/api/character-drafts")
def create_character_draft(request: DraftRequest):
    draft_id = uuid.uuid4().hex
    candidates = generate_character_candidates(request.name.strip(), request.age, count=5, rng=random.Random())
    get_context().drafts[draft_id] = candidates
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
    candidates = get_context().drafts.get(request.draft_id)
    if candidates is None:
        raise HTTPException(status_code=404, detail="建卡候选已过期，请重新生成")
    sheet = CharacterSheet.from_dict(candidates[request.candidate_index].to_dict())
    allocate_occupation_points(
        sheet, request.occupation_id, request.occupation_skills,
        request.occupation_points, request.interest_points,
    )
    record = get_context().characters.create(sheet)
    get_context().drafts.pop(request.draft_id, None)
    return get_context().character_payload(record)


@app.put("/api/characters/{character_id}/skills")
def update_character_skills(character_id: str, request: SkillUpdateRequest):
    record = get_context().characters.get(character_id)
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
    return get_context().character_payload(get_context().characters.save(character_id, record.sheet))


@app.delete("/api/characters/{character_id}")
def delete_character(character_id: str):
    record = get_context().characters.get(character_id)
    games = get_context().referencing_games(character_id=character_id)
    if games:
        titles = "、".join(game.title for game in games[:3])
        suffix = "等" if len(games) > 3 else ""
        raise HTTPException(status_code=409, detail=f"角色卡正被战役「{titles}」{suffix}使用，请先删除这些战役")
    get_context().characters.delete(character_id)
    return {"id": record.id, "name": record.sheet.name, "deleted": True}


@app.get("/api/character-drafts/{draft_id}/candidates/{candidate_index}/occupations/{occupation_id}")
def occupation_preview(draft_id: str, candidate_index: int, occupation_id: int):
    candidates = get_context().drafts.get(draft_id)
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
    return [get_context().module_payload(record) for record in get_context().modules.list()]


@app.get("/api/modules/{module_id}")
def get_module(module_id: str):
    return get_context().module_detail_payload(get_context().modules.get(module_id))


@app.put("/api/modules/{module_id}")
def update_module(module_id: str, request: ModuleUpdateRequest):
    if not request.title.strip():
        raise HTTPException(status_code=400, detail="模组名称不能为空")
    module = KeeperModule.from_dict({
        **request.model_dump(), "title": request.title.strip(),
        "source_name": request.source_name.strip(), "version": 2,
    })
    return get_context().module_detail_payload(get_context().modules.save(module_id, module))


@app.post("/api/modules/{module_id}/analyze", status_code=202)
def analyze_module(module_id: str, reparse: bool = False, review: bool = True):
    context = get_context()
    settings = Settings()
    if (reparse or review) and not settings.mineru_api_key:
        raise HTTPException(status_code=503, detail="尚未配置 MINERU_API_KEY，无法解析 PDF")
    context.modules.get(module_id)
    if context.modules.source_pdf_path(module_id) is None:
        raise HTTPException(status_code=409, detail="该模组未保留原始 PDF，请删除后重新导入")
    job_id = context.module_service.reanalyze(module_id, reparse=reparse, review=review)
    context.module_jobs[module_id] = job_id
    payload = context.jobs.get(job_id)
    payload["module_id"] = module_id
    return payload


@app.get("/api/modules/{module_id}/analysis")
def module_analysis_status(module_id: str):
    context = get_context()
    record = context.modules.get(module_id)
    job_id = context.module_jobs.get(module_id)
    if job_id:
        try:
            payload = context.jobs.get(job_id)
            payload["analysis"] = record.module.analysis
            return payload
        except FileNotFoundError:
            pass
    return {
        "module_id": module_id, "status": "idle", "stage": "尚未启动",
        "error": None, "analysis": record.module.analysis,
    }


@app.get("/api/imports/{job_id}")
def import_status(job_id: str):
    return get_context().jobs.get(job_id)


@app.delete("/api/modules/{module_id}")
def delete_module(module_id: str):
    record = get_context().modules.get(module_id)
    games = get_context().referencing_games(module_id=module_id)
    if games:
        titles = "、".join(game.title for game in games[:3])
        suffix = "等" if len(games) > 3 else ""
        raise HTTPException(status_code=409, detail=f"模组正被战役「{titles}」{suffix}使用，请先删除这些战役")
    get_context().modules.delete(module_id)
    return {"id": record.id, "title": record.module.title, "deleted": True}


@app.post("/api/modules/path", status_code=202)
def import_module_path(request: ModulePathRequest):
    context = get_context()
    source = Path(request.path)
    if not source.exists():
        raise FileNotFoundError(source)
    job_id = context.module_service.import_pdf(source, title=request.title)
    payload = context.jobs.get(job_id)
    payload["job_id"] = job_id
    return payload


@app.post("/api/modules/upload", status_code=202)
async def upload_module(file: UploadFile = File(...), title: str | None = Form(default=None)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请选择 PDF 模组")
    content = await file.read(64 * 1024 * 1024 + 1)
    if len(content) > 64 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF 不能超过 64 MB")
    context = get_context()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=context.data_root) as temporary:
        temporary.write(content)
        temp_path = Path(temporary.name)
    job_id = context.module_service.import_pdf(
        temp_path,
        title=title or Path(file.filename).stem,
        source_name=Path(file.filename).name,
        remove_source=True,
    )
    payload = context.jobs.get(job_id)
    payload["job_id"] = job_id
    return payload


@app.get("/api/games")
def list_games():
    return [get_context().game_payload(record, include_transcript=False) for record in get_context().games.list()]


@app.post("/api/games")
def create_game(request: GameCreateRequest):
    character = get_context().characters.get(request.character_id)
    module = get_context().modules.get(request.module_id)
    if module.module.analysis.get("status") == "failed":
        raise HTTPException(status_code=409, detail="模组解析失败，无法开始战役")
    sheet = CharacterSheet.from_dict(character.sheet.to_dict())
    session = Session(
        investigator=sheet, module=ModuleRuntime(module.module),
        character_id=character.id, module_id=module.id,
    )
    record = get_context().games.create(request.title, character.id, module.id, session)
    return get_context().game_payload(record)


@app.get("/api/games/{game_id}")
def get_game(game_id: str):
    return get_context().game_payload(get_context().games.get(game_id))


@app.delete("/api/games/{game_id}")
def delete_game(game_id: str):
    with get_context().lock(game_id):
        record = get_context().games.get(game_id)
        get_context().games.delete(game_id)
    return {"id": record.id, "title": record.title, "deleted": True}


@app.post("/api/games/{game_id}/messages")
def send_message(game_id: str, request: MessageRequest):
    with get_context().lock(game_id):
        record = get_context().games.get(game_id)
        relevant = record.relevant_history(request.content)
        prompt = KP_SYSTEM_PROMPT
        if relevant:
            prompt += "\n\n## 与当前行动相关的已发生战役记录\n" + "\n".join(f"- {item}" for item in relevant)
        settings = Settings()
        if not settings.is_configured:
            raise HTTPException(status_code=503, detail="尚未配置 DeepSeek API")
        agent = KeeperAgent(record.session, settings, system_prompt=prompt)
        agent.memory.restore(
            record.memory,
            require_reasoning_content=settings.requires_reasoning_content,
        )
        try:
            reply = agent.respond(request.content)
        except Exception as exc:  # noqa: BLE001 - 转换为前端可处理的网关错误
            raise HTTPException(status_code=502, detail=f"模型调用失败: {type(exc).__name__}: {exc}") from exc
        record.transcript.extend([
            TranscriptEntry("user", request.content), TranscriptEntry("assistant", reply),
        ])
        record.memory = agent.memory.snapshot()
        get_context().games.save(record)
        get_context().characters.save(record.character_id, record.session.investigator)
        return {
            "reply": reply,
            "game": get_context().game_payload(record),
            "trace": agent.tracer.summary(),
        }


def main() -> None:
    host = os.environ.get("COC_KEEPER_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("COC_KEEPER_WEB_PORT", "8765"))
    uvicorn.run("coc_keeper.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
