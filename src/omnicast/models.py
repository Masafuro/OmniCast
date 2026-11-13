"""Domain models and API schemas for OmniCast rev1 & rev2."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

BlockStatus = Literal["unbuilt", "dirty", "ready", "locked"]
VoiceMode = Literal["design", "clone"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:10]
    return f"{prefix}{short}" if prefix else short


class VoiceProfile(BaseModel):
    """Character / speaker voice definition supporting both Design and Clone modes."""

    id: str
    name: str
    role: str = ""
    mode: VoiceMode = "design"
    is_builtin: bool = False
    is_customized: bool = False
    lang: str = "Auto"
    default_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    default_instruct: str = ""
    # Clone fields
    ref_audio: str | None = None
    ref_audio_duration: float | None = None
    ref_text: str = ""
    ref_version: int = 0
    # Design fields
    gender: str = "Auto"
    age: str = "Auto"
    pitch: str = "Auto"
    style: str = "Auto"
    english_accent: str = "Auto"
    chinese_dialect: str = "Auto"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class Take(BaseModel):
    """A single generated audio take for a dialogue block."""

    id: str
    file: str
    duration: float = 0.0
    input_hash: str
    created_at: str = Field(default_factory=utc_now_iso)


class Block(BaseModel):
    """An utterance unit combining script text, voice assignment, takes, and pause."""

    id: str = Field(default_factory=lambda: new_id("blk_"))
    voice_id: str = "Alice"
    text: str
    tts_text: str | None = None
    lang: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    style: str | None = None
    instruct: str | None = None
    pause_after: float = Field(default=0.45, ge=0.0, le=10.0)
    takes: list[Take] = Field(default_factory=list)
    selected_take_id: str | None = None
    locked: bool = False

    def effective_tts_text(self) -> str:
        if self.tts_text is not None and self.tts_text.strip():
            return self.tts_text.strip()
        return self.text.strip()

    def selected_take(self) -> Take | None:
        if not self.selected_take_id:
            return None
        for take in self.takes:
            if take.id == self.selected_take_id:
                return take
        return None


class Project(BaseModel):
    """An OmniCast podcast or narration episode project."""

    id: str = Field(default_factory=lambda: new_id("proj_"))
    title: str = "Untitled Episode"
    default_lang: str = "Auto"
    default_turn_pause: float = Field(default=0.45, ge=0.0, le=10.0)
    trim_silence: bool = True
    normalize_loudness: bool = True
    blocks: list[Block] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


def compute_block_input_hash(
    block: Block,
    project: Project,
    voice: VoiceProfile | None = None,
) -> str:
    """Compute a stable hash of the inputs that affect TTS output for a block."""
    effective_lang = (
        block.lang
        or (voice.lang if voice and voice.lang and voice.lang != "Auto" else None)
        or project.default_lang
        or "Auto"
    )
    effective_speed = block.speed if block.speed is not None else (
        voice.default_speed if voice else 1.0
    )
    effective_instruct = (
        block.instruct
        if block.instruct is not None
        else (voice.default_instruct if voice else "")
    )
    payload: dict[str, object] = {
        "voice_id": block.voice_id,
        "tts_text": block.effective_tts_text(),
        "lang": effective_lang,
        "speed": round(effective_speed, 3),
        "style": block.style or (voice.style if voice else "Auto") or "Auto",
    }
    if voice is not None:
        payload["voice_mode"] = voice.mode
        if voice.mode == "clone":
            payload["ref_version"] = voice.ref_version
            payload["ref_text"] = voice.ref_text
            payload["instruct"] = effective_instruct
        else:
            payload["design"] = [
                voice.gender,
                voice.age,
                voice.pitch,
                voice.english_accent,
                voice.chinese_dialect,
            ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def get_block_status(
    block: Block,
    project: Project,
    voice: VoiceProfile | None = None,
) -> BlockStatus:
    """Derive display and batch-build status for a block."""
    if block.locked:
        return "locked"
    selected = block.selected_take()
    if selected is None:
        return "unbuilt"
    if selected.input_hash != compute_block_input_hash(block, project, voice):
        return "dirty"
    return "ready"


# --- API Request / Response Schemas ---


class BlockView(Block):
    """Block serialized with derived status and current input hash."""

    status: BlockStatus
    current_input_hash: str

    @classmethod
    def from_block(
        cls,
        block: Block,
        project: Project,
        voice: VoiceProfile | None = None,
    ) -> BlockView:
        return cls(
            **block.model_dump(),
            status=get_block_status(block, project, voice),
            current_input_hash=compute_block_input_hash(block, project, voice),
        )


class ProjectView(BaseModel):
    """Project serialized with enriched BlockViews."""

    id: str
    title: str
    default_lang: str
    default_turn_pause: float
    trim_silence: bool
    normalize_loudness: bool
    blocks: list[BlockView]
    created_at: str
    updated_at: str

    @classmethod
    def from_project(
        cls,
        project: Project,
        voices_by_id: dict[str, VoiceProfile] | None = None,
    ) -> ProjectView:
        lookup = voices_by_id or {}
        return cls(
            id=project.id,
            title=project.title,
            default_lang=project.default_lang,
            default_turn_pause=project.default_turn_pause,
            trim_silence=project.trim_silence,
            normalize_loudness=project.normalize_loudness,
            blocks=[
                BlockView.from_block(b, project, lookup.get(b.voice_id))
                for b in project.blocks
            ],
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


class ProjectSummary(BaseModel):
    id: str
    title: str
    block_count: int
    updated_at: str


class ProjectCreate(BaseModel):
    title: str = Field(default="New Episode", min_length=1, max_length=120)
    default_lang: str = "Auto"
    default_turn_pause: float = Field(default=0.45, ge=0.0, le=10.0)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    default_lang: str | None = None
    default_turn_pause: float | None = Field(default=None, ge=0.0, le=10.0)
    trim_silence: bool | None = None
    normalize_loudness: bool | None = None


class ImportScriptRequest(BaseModel):
    script: str
    mode: Literal["replace", "append"] = "replace"


class ImportScriptResponse(BaseModel):
    project: ProjectView
    imported_count: int
    warnings: list[str] = Field(default_factory=list)


class BlockCreate(BaseModel):
    voice_id: str = "Alice"
    text: str = ""
    pause_after: float | None = Field(default=None, ge=0.0, le=10.0)
    insert_index: int | None = None


class BlockUpdate(BaseModel):
    voice_id: str | None = None
    text: str | None = None
    tts_text: str | None = None
    lang: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    style: str | None = None
    instruct: str | None = None
    pause_after: float | None = Field(default=None, ge=0.0, le=10.0)
    selected_take_id: str | None = None
    locked: bool | None = None


class ReorderBlocksRequest(BaseModel):
    block_ids: list[str]


class GenerateBatchResponse(BaseModel):
    project: ProjectView
    generated_block_ids: list[str]
    skipped_count: int


class ExportRequest(BaseModel):
    format: Literal["wav", "mp3"] = "wav"


class ExportResponse(BaseModel):
    file: str
    download_url: str
    duration: float
    block_count: int


# --- Voice / Cast API Schemas ---


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    role: str = ""
    lang: str = "Auto"
    default_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    default_instruct: str = ""
    ref_text: str = ""
    gender: str = "Auto"
    age: str = "Auto"
    pitch: str = "Auto"
    style: str = "Auto"
    english_accent: str = "Auto"
    chinese_dialect: str = "Auto"


class VoiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    role: str | None = None
    mode: VoiceMode | None = None
    lang: str | None = None
    default_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    default_instruct: str | None = None
    ref_text: str | None = None
    gender: str | None = None
    age: str | None = None
    pitch: str | None = None
    style: str | None = None
    english_accent: str | None = None
    chinese_dialect: str | None = None


class DesignPreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    lang: str = "Auto"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    gender: str = "Auto"
    age: str = "Auto"
    pitch: str = "Auto"
    style: str = "Auto"
    english_accent: str = "Auto"
    chinese_dialect: str = "Auto"


class DesignPreviewResponse(BaseModel):
    preview_file: str
    audio_url: str
    duration: float


class AdoptPreviewRequest(BaseModel):
    preview_file: str
    ref_text: str = ""


class ClonePreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    lang: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    instruct: str | None = None


class ClonePreviewResponse(BaseModel):
    preview_file: str
    audio_url: str
    duration: float
    mode_used: VoiceMode
