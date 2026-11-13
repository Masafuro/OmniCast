"""FastAPI application for OmniCast Studio rev1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from omnicast.audio import AudioProcessingError
from omnicast.characters import DEFAULT_CHARACTERS, resolve_character
from omnicast.config import Settings
from omnicast.models import (
    Block,
    BlockCreate,
    BlockUpdate,
    ExportRequest,
    ExportResponse,
    GenerateBatchResponse,
    ImportScriptRequest,
    ImportScriptResponse,
    Project,
    ProjectCreate,
    ProjectSummary,
    ProjectUpdate,
    ProjectView,
    ReorderBlocksRequest,
)
from omnicast.omnivoice import (
    GradioOmniVoiceClient,
    MockOmniVoiceClient,
    OmniVoiceClient,
    OmniVoiceError,
)
from omnicast.parser import export_script, parse_script
from omnicast.service import BlockNotFoundError, StudioService
from omnicast.storage import InvalidIdentifierError, ProjectNotFoundError, ProjectStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _find_block_or_404(project: Project, block_id: str) -> Block:
    for block in project.blocks:
        if block.id == block_id:
            return block
    raise HTTPException(status_code=404, detail=f"Block not found: {block_id}")


def create_app(
    settings: Settings | None = None,
    client: OmniVoiceClient | None = None,
) -> FastAPI:
    """Build and configure the FastAPI application."""
    cfg = settings or Settings.from_env()
    tts_client: OmniVoiceClient = client or (
        MockOmniVoiceClient() if cfg.use_mock else GradioOmniVoiceClient(cfg.omnivoice_url)
    )
    store = ProjectStore(cfg.data_dir)
    service = StudioService(store=store, client=tts_client)

    app = FastAPI(title="OmniCast Studio", version="0.1.0")

    def _load_or_404(project_id: str) -> Project:
        try:
            return store.load(project_id)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "omnivoice": tts_client.health_check(),
            "data_dir": str(cfg.data_dir),
        }

    @app.get("/api/characters")
    def list_characters() -> list[dict[str, str]]:
        return [c.to_dict() for c in DEFAULT_CHARACTERS]

    @app.get("/api/projects", response_model=list[ProjectSummary])
    def list_projects() -> list[ProjectSummary]:
        return store.list_projects()

    @app.post("/api/projects", response_model=ProjectView, status_code=201)
    def create_project(payload: ProjectCreate) -> ProjectView:
        project = Project(
            title=payload.title.strip(),
            default_lang=payload.default_lang,
            default_turn_pause=payload.default_turn_pause,
        )
        store.save(project)
        return ProjectView.from_project(project)

    @app.get("/api/projects/{project_id}", response_model=ProjectView)
    def get_project(project_id: str) -> ProjectView:
        return ProjectView.from_project(_load_or_404(project_id))

    @app.patch("/api/projects/{project_id}", response_model=ProjectView)
    def update_project(project_id: str, payload: ProjectUpdate) -> ProjectView:
        project = _load_or_404(project_id)
        if payload.title is not None:
            project.title = payload.title.strip()
        if payload.default_lang is not None:
            project.default_lang = payload.default_lang
        if payload.default_turn_pause is not None:
            project.default_turn_pause = payload.default_turn_pause
        if payload.trim_silence is not None:
            project.trim_silence = payload.trim_silence
        if payload.normalize_loudness is not None:
            project.normalize_loudness = payload.normalize_loudness
        store.save(project)
        return ProjectView.from_project(project)

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str) -> None:
        try:
            store.delete(project_id)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/import-script", response_model=ImportScriptResponse)
    def import_script_endpoint(
        project_id: str, payload: ImportScriptRequest
    ) -> ImportScriptResponse:
        project = _load_or_404(project_id)
        new_blocks, warnings = parse_script(
            payload.script, default_pause=project.default_turn_pause
        )
        if payload.mode == "replace":
            project.blocks = new_blocks
        else:
            project.blocks.extend(new_blocks)
        store.save(project)
        return ImportScriptResponse(
            project=ProjectView.from_project(project),
            imported_count=len(new_blocks),
            warnings=warnings,
        )

    @app.get("/api/projects/{project_id}/export-script", response_class=PlainTextResponse)
    def export_script_endpoint(project_id: str) -> PlainTextResponse:
        project = _load_or_404(project_id)
        return PlainTextResponse(export_script(project))

    @app.post("/api/projects/{project_id}/blocks", response_model=ProjectView, status_code=201)
    def add_block(project_id: str, payload: BlockCreate) -> ProjectView:
        project = _load_or_404(project_id)
        preset, _ = resolve_character(payload.voice_id)
        block = Block(
            voice_id=preset.id,
            text=payload.text,
            pause_after=(
                payload.pause_after
                if payload.pause_after is not None
                else project.default_turn_pause
            ),
        )
        if payload.insert_index is None or payload.insert_index >= len(project.blocks):
            project.blocks.append(block)
        else:
            idx = max(0, payload.insert_index)
            project.blocks.insert(idx, block)
        store.save(project)
        return ProjectView.from_project(project)

    @app.patch("/api/projects/{project_id}/blocks/{block_id}", response_model=ProjectView)
    def update_block(
        project_id: str, block_id: str, payload: BlockUpdate
    ) -> ProjectView:
        project = _load_or_404(project_id)
        block = _find_block_or_404(project, block_id)
        fields = payload.model_fields_set

        if "voice_id" in fields and payload.voice_id is not None:
            preset, _ = resolve_character(payload.voice_id)
            block.voice_id = preset.id
        if "text" in fields and payload.text is not None:
            block.text = payload.text
        if "tts_text" in fields:
            block.tts_text = payload.tts_text or None
        if "lang" in fields:
            block.lang = payload.lang or None
        if "speed" in fields:
            block.speed = payload.speed
        if "style" in fields:
            block.style = payload.style or None
        if "pause_after" in fields and payload.pause_after is not None:
            block.pause_after = payload.pause_after
        if "locked" in fields and payload.locked is not None:
            block.locked = payload.locked
        if "selected_take_id" in fields and payload.selected_take_id is not None:
            valid_ids = {t.id for t in block.takes}
            if payload.selected_take_id not in valid_ids:
                raise HTTPException(
                    status_code=400, detail=f"Unknown take_id: {payload.selected_take_id}"
                )
            block.selected_take_id = payload.selected_take_id

        store.save(project)
        return ProjectView.from_project(project)

    @app.delete("/api/projects/{project_id}/blocks/{block_id}", response_model=ProjectView)
    def delete_block(project_id: str, block_id: str) -> ProjectView:
        project = _load_or_404(project_id)
        before = len(project.blocks)
        project.blocks = [b for b in project.blocks if b.id != block_id]
        if len(project.blocks) == before:
            raise HTTPException(status_code=404, detail=f"Block not found: {block_id}")
        store.save(project)
        return ProjectView.from_project(project)

    @app.post("/api/projects/{project_id}/blocks/reorder", response_model=ProjectView)
    def reorder_blocks(
        project_id: str, payload: ReorderBlocksRequest
    ) -> ProjectView:
        project = _load_or_404(project_id)
        by_id = {b.id: b for b in project.blocks}
        if set(payload.block_ids) != set(by_id.keys()) or len(payload.block_ids) != len(
            project.blocks
        ):
            raise HTTPException(
                status_code=400,
                detail="block_ids must contain the exact set of existing block IDs.",
            )
        project.blocks = [by_id[bid] for bid in payload.block_ids]
        store.save(project)
        return ProjectView.from_project(project)

    @app.post(
        "/api/projects/{project_id}/blocks/{block_id}/generate",
        response_model=ProjectView,
    )
    def generate_block(project_id: str, block_id: str) -> ProjectView:
        try:
            return service.generate_block_take(project_id, block_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BlockNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, InvalidIdentifierError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OmniVoiceError, AudioProcessingError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/generate", response_model=GenerateBatchResponse)
    def generate_batch(project_id: str) -> GenerateBatchResponse:
        try:
            return service.generate_batch(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, InvalidIdentifierError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OmniVoiceError, AudioProcessingError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/takes/{filename}")
    def get_take_audio(project_id: str, filename: str) -> FileResponse:
        try:
            path = store.take_path(project_id, filename)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Audio file not found: {filename}")
        return FileResponse(path, media_type="audio/wav", filename=filename)

    @app.post("/api/projects/{project_id}/export", response_model=ExportResponse)
    def export_audio(project_id: str, payload: ExportRequest) -> ExportResponse:
        try:
            return service.export_episode(project_id, fmt=payload.format)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AudioProcessingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/exports/{filename}")
    def download_export(project_id: str, filename: str) -> FileResponse:
        try:
            path = store.export_path(project_id, filename)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Export not found: {filename}")
        media = "audio/mpeg" if filename.lower().endswith(".mp3") else "audio/wav"
        return FileResponse(path, media_type=media, filename=filename)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/manifest.webmanifest", include_in_schema=False)
        def manifest() -> FileResponse:
            return FileResponse(
                STATIC_DIR / "manifest.webmanifest",
                media_type="application/manifest+json",
            )

    return app
