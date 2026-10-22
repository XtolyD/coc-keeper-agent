# -*- coding: utf-8 -*-
import time

from coc_keeper.module_pipeline import ModuleImportRequest
from coc_keeper.module_service import ModuleApplicationService
from coc_keeper.module_store import ModuleStore
from coc_keeper.modules import KeeperModule, ModuleScene
from coc_keeper.web_jobs import JobManager


def _module(title="服务模组"):
    return KeeperModule(title, "service.pdf", [
        ModuleScene("scene-001", "门厅", "当前场景", 1, 1, "门厅里有一把钥匙。"),
    ])


class _FakePipeline:
    def run(self, request: ModuleImportRequest, *, progress=None):
        if progress:
            progress("假解析")
        return _module(request.title or "未命名")


def _wait(jobs, job_id):
    for _ in range(200):
        payload = jobs.get(job_id)
        if payload["status"] != "running":
            return payload
        time.sleep(0.01)
    return payload


def test_service_import_creates_module_and_removes_temp_source(tmp_path):
    store = ModuleStore(tmp_path / "modules")
    jobs = JobManager(max_workers=1)
    service = ModuleApplicationService(store, jobs, data_root=tmp_path / "data")
    service._pipeline = lambda report, review=True: _FakePipeline()
    source = tmp_path / "upload.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    job_id = service.import_pdf(source, title="服务导入", remove_source=True)
    payload = _wait(jobs, job_id)
    assert payload["status"] == "completed", payload
    module_id = payload["result"]["module_id"]
    record = store.get(module_id)
    assert record.module.title == "服务导入"
    assert store.source_pdf_path(module_id) is not None
    assert not source.exists()


def test_service_reanalyze_structure_only_updates_existing_module(tmp_path, monkeypatch):
    import coc_keeper.module_service as service_module

    store = ModuleStore(tmp_path / "modules")
    jobs = JobManager(max_workers=1)
    service = ModuleApplicationService(store, jobs, data_root=tmp_path / "data")
    source = tmp_path / "module.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    record = store.create(_module(), source_pdf=source)

    class _Analyzer:
        def analyze(self, module):
            module.analysis = {"mode": "llm", "status": "complete"}
            return module

    service._analyzer = lambda report: _Analyzer()
    monkeypatch.setattr(service_module, "Settings", lambda: type("S", (), {"is_configured": True})())
    job_id = service.reanalyze(record.id, reparse=False, review=False)
    payload = _wait(jobs, job_id)
    assert payload["status"] == "completed", payload
    assert store.get(record.id).module.analysis["status"] == "complete"
