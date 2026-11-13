"""Domain models and API schemas for OmniCast rev1."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

BlockStatus = Literal["unbuilt", "dirty", "ready", "locked"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:10]
    return f"{prefix}{short}" if prefix else short


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


def compute_block_input_hash(block: Block, project: Project) -> str:
    """Compute a stable hash of the inputs that affect TTS output for a block."""
    payload = {
        "voice_id": block.voice_id,
        "tts_text": block.effective_tts_text(),
        "lang": block.lang or project.default_lang or "Auto",
        "speed": round(block.speed if block.speed is not None else 1.0, 3),
        "style": block.style or "Auto",
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def get_block_status(block: Block, project: Project) -> BlockStatus:
    """Derive display and batch-build status for a block."""
    if block.locked:
        return "locked"
    selected = block.selected_take()
    if selected is None:
        return "unbuilt"
    if selected.input_hash != compute_block_input_hash(block, project):
        return "dirty"
    return "ready"


# --- API Request / Response Schemas ---


class BlockView(Block):
    """Block serialized with derived status and current input hash."""

    status: BlockStatus
    current_input_hash: str

    @classmethod
    def from_block(cls, block: Block, project: Project) -> BlockView:
        return cls(
            **block.model_dump(),
            status=get_block_status(block, project),
            current_input_hash=compute_block_input_hash(block, project),
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
    def from_project(cls, project: Project) -> ProjectView:
        return cls(
            id=project.id,
            title=project.title,
            default_lang=project.default_lang,
            default_turn_pause=project.default_turn_pause,
            trim_silence=project.trim_silence,
            normalize_loudness=project.normalize_loudness,
            blocks=[BlockView.from_block(b, project) for b in project.blocks],
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
