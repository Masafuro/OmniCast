"""FastAPI application for OmniCast Studio."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from omnicast.audio import AudioProcessingError
from omnicast.characters import OMNIVOICE_DESIGN_OPTIONS
from omnicast.config import Settings
from omnicast.models import (
    AdoptPreviewRequest,
    Block,
    BlockCreate,
    BlockUpdate,
    ClonePreviewRequest,
    ClonePreviewResponse,
    DesignPreviewRequest,
    DesignPreviewResponse,
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
    VoiceCreate,
    VoiceProfile,
    VoiceUpdate,
)
from omnicast.omnivoice import (
    GradioOmniVoiceClient,
    MockOmniVoiceClient,
    OmniVoiceClient,
    OmniVoiceError,
)
from omnicast.parser import export_script, parse_script
from omnicast.service import BlockNotFoundError, StudioService
from omnicast.storage import (
    InvalidIdentifierError,
    ProjectNotFoundError,
    ProjectStore,
    VoiceNotFoundError,
    VoiceStore,
)

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
    voice_store = VoiceStore(cfg.data_dir)
    service = StudioService(store=store, voice_store=voice_store, client=tts_client)

    app = FastAPI(title="OmniCast Studio", version="0.2.0")

    def _load_or_404(project_id: str) -> Project:
        try:
            return store.load(project_id)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _load_voice_or_404(voice_id: str) -> VoiceProfile:
        try:
            return voice_store.get(voice_id)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VoiceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "omnivoice": tts_client.health_check(),
            "data_dir": str(cfg.data_dir),
        }

    # --- Characters / Voices (Cast) ---

    @app.get("/api/characters", response_model=list[VoiceProfile])
    def list_characters() -> list[VoiceProfile]:
        return voice_store.list_voices()

    @app.get("/api/voices/options")
    def voice_design_options() -> dict[str, list[str]]:
        return OMNIVOICE_DESIGN_OPTIONS

    @app.get("/api/voices", response_model=list[VoiceProfile])
    def list_voices() -> list[VoiceProfile]:
        return voice_store.list_voices()

    @app.post("/api/voices", response_model=VoiceProfile, status_code=201)
    def create_voice(payload: VoiceCreate) -> VoiceProfile:
        try:
            return voice_store.create(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/voices/design-preview", response_model=DesignPreviewResponse)
    def design_preview(payload: DesignPreviewRequest) -> DesignPreviewResponse:
        try:
            return service.generate_design_preview(payload)
        except (OmniVoiceError, AudioProcessingError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/voices/drafts/{filename}")
    def get_draft_audio(filename: str) -> FileResponse:
        try:
            path = voice_store.draft_path(filename)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Preview file not found: {filename}")
        return FileResponse(path, media_type="audio/wav", filename=filename)

    @app.delete("/api/voices/drafts/{filename}")
    def delete_draft_audio(filename: str) -> dict[str, str]:
        try:
            deleted = voice_store.delete_draft(filename)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Preview file not found: {filename}")
        return {"status": "deleted", "filename": filename}

    @app.get("/api/voices/{voice_id}", response_model=VoiceProfile)
    def get_voice(voice_id: str) -> VoiceProfile:
        return _load_voice_or_404(voice_id)

    @app.patch("/api/voices/{voice_id}", response_model=VoiceProfile)
    def update_voice(voice_id: str, payload: VoiceUpdate) -> VoiceProfile:
        voice = _load_voice_or_404(voice_id)
        fields = payload.model_fields_set

        if "name" in fields and payload.name is not None:
            new_name = payload.name.strip()
            for other in voice_store.list_voices():
                if other.id != voice.id and other.name.lower() == new_name.lower():
                    raise HTTPException(
                        status_code=400, detail=f"Character name already exists: {new_name}"
                    )
            voice.name = new_name
        if "role" in fields and payload.role is not None:
            voice.role = payload.role
        if "mode" in fields and payload.mode is not None:
            if payload.mode == "clone" and not voice_store.ref_audio_path(voice.id).exists():
                raise HTTPException(
                    status_code=400, detail="Cannot switch to clone mode without reference audio."
                )
            voice.mode = payload.mode
        if "lang" in fields and payload.lang is not None:
            voice.lang = payload.lang
        if "default_speed" in fields and payload.default_speed is not None:
            voice.default_speed = payload.default_speed
        if "default_instruct" in fields and payload.default_instruct is not None:
            voice.default_instruct = payload.default_instruct
        if "ref_text" in fields and payload.ref_text is not None:
            voice.ref_text = payload.ref_text
        if "gender" in fields and payload.gender is not None:
            voice.gender = payload.gender
        if "age" in fields and payload.age is not None:
            voice.age = payload.age
        if "pitch" in fields and payload.pitch is not None:
            voice.pitch = payload.pitch
        if "style" in fields and payload.style is not None:
            voice.style = payload.style
        if "english_accent" in fields and payload.english_accent is not None:
            voice.english_accent = payload.english_accent
        if "chinese_dialect" in fields and payload.chinese_dialect is not None:
            voice.chinese_dialect = payload.chinese_dialect

        return voice_store.save(voice)

    @app.delete("/api/voices/{voice_id}")
    def delete_voice(voice_id: str) -> dict[str, str]:
        try:
            action = voice_store.delete(voice_id)
            return {"status": action, "id": voice_id}
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VoiceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/voices/{voice_id}/ref-audio")
    def get_voice_ref_audio(voice_id: str) -> FileResponse:
        _load_voice_or_404(voice_id)
        path = voice_store.ref_audio_path(voice_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Reference audio not configured.")
        return FileResponse(path, media_type="audio/wav", filename=f"{voice_id}_ref.wav")

    @app.post("/api/voices/{voice_id}/adopt-preview", response_model=VoiceProfile)
    def adopt_preview(voice_id: str, payload: AdoptPreviewRequest) -> VoiceProfile:
        try:
            return service.adopt_preview_as_ref(
                voice_id, preview_file=payload.preview_file, ref_text=payload.ref_text
            )
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (VoiceNotFoundError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AudioProcessingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/voices/{voice_id}/ref-audio", response_model=VoiceProfile)
    async def upload_ref_audio(
        voice_id: str, file: UploadFile = File(...)
    ) -> VoiceProfile:
        _load_voice_or_404(voice_id)
        suffix = Path(file.filename or "audio.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            shutil.copyfileobj(file.file, tmp)
        try:
            return service.set_uploaded_ref_audio(voice_id, tmp_path)
        except AudioProcessingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @app.post("/api/voices/{voice_id}/clone-preview", response_model=ClonePreviewResponse)
    def clone_preview(
        voice_id: str, payload: ClonePreviewRequest
    ) -> ClonePreviewResponse:
        try:
            return service.generate_voice_test(voice_id, payload)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VoiceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OmniVoiceError, AudioProcessingError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/voices/{voice_id}/export")
    def export_voice(voice_id: str) -> Response:
        try:
            zip_bytes, filename = service.export_voice_zip(voice_id)
        except InvalidIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VoiceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        ascii_fallback = "".join(c if ord(c) < 128 and c not in '"\\' else "_" for c in filename)
        if not ascii_fallback.endswith(".omnicast-voice.zip"):
            ascii_fallback = "voice.omnicast-voice.zip"
        disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(filename)}'
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": disposition},
        )

    @app.post("/api/voices/import", response_model=VoiceProfile)
    async def import_voice(
        file: UploadFile = File(...),
        conflict: Literal["rename", "overwrite"] = Form("rename"),
    ) -> VoiceProfile:
        zip_bytes = await file.read()
        try:
            return service.import_voice_zip(zip_bytes, conflict=conflict)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AudioProcessingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # --- Projects ---

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
        return service.project_view(project)

    @app.get("/api/projects/{project_id}", response_model=ProjectView)
    def get_project(project_id: str) -> ProjectView:
        return service.project_view(_load_or_404(project_id))

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
        return service.project_view(project)

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
        voices = voice_store.list_voices()
        new_blocks, warnings = parse_script(
            payload.script,
            default_pause=project.default_turn_pause,
            voices=voices,
        )
        if payload.mode == "replace":
            project.blocks = new_blocks
        else:
            project.blocks.extend(new_blocks)
        store.save(project)
        return ImportScriptResponse(
            project=service.project_view(project),
            imported_count=len(new_blocks),
            warnings=warnings,
        )

    @app.get("/api/projects/{project_id}/export-script", response_class=PlainTextResponse)
    def export_script_endpoint(project_id: str) -> PlainTextResponse:
        project = _load_or_404(project_id)
        return PlainTextResponse(export_script(project, voices=voice_store.list_voices()))

    @app.post("/api/projects/{project_id}/blocks", response_model=ProjectView, status_code=201)
    def add_block(project_id: str, payload: BlockCreate) -> ProjectView:
        project = _load_or_404(project_id)
        voice, _ = voice_store.resolve_voice(payload.voice_id)
        block = Block(
            voice_id=voice.id,
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
        return service.project_view(project)

    @app.patch("/api/projects/{project_id}/blocks/{block_id}", response_model=ProjectView)
    def update_block(
        project_id: str, block_id: str, payload: BlockUpdate
    ) -> ProjectView:
        project = _load_or_404(project_id)
        block = _find_block_or_404(project, block_id)
        fields = payload.model_fields_set

        if "voice_id" in fields and payload.voice_id is not None:
            voice, _ = voice_store.resolve_voice(payload.voice_id)
            block.voice_id = voice.id
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
        if "instruct" in fields:
            block.instruct = payload.instruct if payload.instruct else None
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
        return service.project_view(project)

    @app.delete("/api/projects/{project_id}/blocks/{block_id}", response_model=ProjectView)
    def delete_block(project_id: str, block_id: str) -> ProjectView:
        project = _load_or_404(project_id)
        before = len(project.blocks)
        project.blocks = [b for b in project.blocks if b.id != block_id]
        if len(project.blocks) == before:
            raise HTTPException(status_code=404, detail=f"Block not found: {block_id}")
        store.save(project)
        return service.project_view(project)

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
        return service.project_view(project)

    @app.post(
        "/api/projects/{project_id}/blocks/{block_id}/generate",
        response_model=ProjectView,
    )
    def generate_block(project_id: str, block_id: str) -> ProjectView:
        try:
            return service.generate_block_take(project_id, block_id)
        except (ProjectNotFoundError, BlockNotFoundError) as exc:
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
