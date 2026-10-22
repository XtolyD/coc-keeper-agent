# -*- coding: utf-8 -*-
"""模组应用服务：把解析流水线、仓储与后台任务编排在一起。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .agent.llm import LLMClient
from .config import PROJECT_ROOT, Settings
from .docparser import MinerUClient
from .module_analysis import LLMModuleAnalyzer
from .module_pipeline import ModuleImportPipeline, ModuleImportRequest
from .module_pipeline.mineru_parser import CachedMinerUDocumentParser
from .module_pipeline.review import LLMModuleReviewer
from .module_store import ModuleRecord, ModuleStore
from .modules import KeeperModule
from .vision import VisionClient
from .web_jobs import JobManager


class ModuleApplicationService:
    """导入/重新分析模组的用例层。"""

    def __init__(
        self,
        store: ModuleStore,
        jobs: JobManager,
        *,
        data_root: str | Path | None = None,
    ):
        self.store = store
        self.jobs = jobs
        self.data_root = Path(data_root or PROJECT_ROOT / "data")

    def import_pdf(
        self,
        source_path: str | Path,
        *,
        title: str | None = None,
        source_name: str | None = None,
        remove_source: bool = False,
    ) -> str:
        source = Path(source_path)

        def run(report: Callable[[str], None]) -> dict:
            try:
                module = self._pipeline(report).run(
                    ModuleImportRequest(
                        pdf_path=source,
                        title=title,
                        source_name=source_name or source.name,
                    ),
                    progress=report,
                )
                record = self.store.create(module, source_pdf=source)
                return {"module_id": record.id, "module": record.summary()}
            finally:
                if remove_source:
                    source.unlink(missing_ok=True)

        return self.jobs.submit("module-import", run)

    def reanalyze(
        self,
        module_id: str,
        *,
        reparse: bool = False,
        review: bool = True,
    ) -> str:
        record = self.store.get(module_id)
        source = self.store.source_pdf_path(module_id)
        if source is None:
            raise ValueError("该模组未保留原始 PDF，请删除后重新导入")

        def run(report: Callable[[str], None]) -> dict:
            if not reparse and not review:
                report("重新结构分析")
                module = record.module
                analyzer = self._analyzer(report)
                if analyzer is None:
                    raise RuntimeError("未配置 DeepSeek API，无法进行结构分析")
                module = analyzer.analyze(module)
            else:
                module = self._pipeline(report, review=review).run(
                    ModuleImportRequest(
                        pdf_path=source,
                        title=record.module.title,
                        source_name=record.module.source_name,
                        reparse=reparse,
                    ),
                    progress=report,
                )
            saved = self.store.save(module_id, module)
            return {"module_id": module_id, "module": saved.summary()}

        return self.jobs.submit("module-reanalyze", run)

    def sync_import(
        self,
        source_path: str | Path,
        *,
        title: str | None = None,
        source_name: str | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> ModuleRecord:
        """CLI 同步导入（不经过后台任务）。"""
        source = Path(source_path)
        module = self.load_pdf(source, title=title, source_name=source_name, progress=progress)
        return self.store.create(module, source_pdf=source)

    def load_pdf(
        self,
        source_path: str | Path,
        *,
        title: str | None = None,
        source_name: str | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> KeeperModule:
        """同步解析 PDF，不落模组库（CLI 临时加载用）。"""
        source = Path(source_path)
        return self._pipeline(progress or (lambda _stage: None)).run(
            ModuleImportRequest(pdf_path=source, title=title, source_name=source_name or source.name),
            progress=progress,
        )

    def _pipeline(
        self,
        report: Callable[[str], None],
        *,
        review: bool = True,
    ) -> ModuleImportPipeline:
        settings = Settings()
        if not settings.mineru_api_key:
            raise RuntimeError("未配置 MINERU_API_KEY，无法解析 PDF")
        client = MinerUClient(
            api_key=settings.mineru_api_key,
            base_url=settings.mineru_base_url,
            poll_interval=settings.mineru_poll_interval,
        )
        cache_root = Path(settings.mineru_cache_dir) if settings.mineru_cache_dir else self.data_root / "mineru"
        parser = CachedMinerUDocumentParser(client, cache_root)
        reviewer = LLMModuleReviewer(VisionClient()) if review and settings.is_configured else None
        analyzer = self._analyzer(report)
        return ModuleImportPipeline(parser=parser, reviewer=reviewer, analyzer=analyzer)

    @staticmethod
    def _analyzer(report: Callable[[str], None]) -> LLMModuleAnalyzer | None:
        settings = Settings()
        if not settings.is_configured:
            return None
        return LLMModuleAnalyzer(LLMClient(settings), progress=report)
