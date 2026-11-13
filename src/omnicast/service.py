"""Core orchestration service for block synthesis and episode export."""

from __future__ import annotations

import re

from omnicast.audio import export_project_audio, ffprobe_duration
from omnicast.characters import get_character
from omnicast.models import (
    Block,
    ExportResponse,
    GenerateBatchResponse,
    Project,
    ProjectView,
    Take,
    compute_block_input_hash,
)
from omnicast.omnivoice import DesignSynthesisRequest, OmniVoiceClient
from omnicast.storage import ProjectStore


class BlockNotFoundError(LookupError):
    """Raised when a block ID is not present in the project."""


def _find_block(project: Project, block_id: str) -> Block:
    for block in project.blocks:
        if block.id == block_id:
            return block
    raise BlockNotFoundError(f"Block not found: {block_id}")


def _safe_slug(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", title.strip()).strip("_")
    return slug[:60] or "episode"


class StudioService:
    """Coordinates TTS synthesis, take history, and episode audio export."""

    def __init__(self, store: ProjectStore, client: OmniVoiceClient) -> None:
        self.store = store
        self.client = client

    def generate_block_take(self, project_id: str, block_id: str) -> ProjectView:
        project = self.store.load(project_id)
        block = _find_block(project, block_id)
        self._synthesize_into_block(project, block)
        self.store.save(project)
        return ProjectView.from_project(project)

    def generate_batch(self, project_id: str) -> GenerateBatchResponse:
        project = self.store.load(project_id)
        generated_ids: list[str] = []
        skipped = 0

        for block in project.blocks:
            if not block.locked and block.effective_tts_text():
                self._synthesize_into_block(project, block)
                generated_ids.append(block.id)
            else:
                skipped += 1

        if generated_ids:
            self.store.save(project)

        return GenerateBatchResponse(
            project=ProjectView.from_project(project),
            generated_block_ids=generated_ids,
            skipped_count=skipped,
        )

    def _synthesize_into_block(self, project: Project, block: Block) -> Take:
        tts_text = block.effective_tts_text()
        if not tts_text:
            raise ValueError(f"Block {block.id} has empty text.")

        preset = get_character(block.voice_id)
        req = DesignSynthesisRequest(
            text=tts_text,
            lang=block.lang or project.default_lang or "Auto",
            gender=preset.gender,
            age=preset.age,
            pitch=preset.pitch,
            style=block.style or preset.style,
            english_accent=preset.english_accent,
            chinese_dialect=preset.chinese_dialect,
            speed=block.speed if block.speed is not None else 1.0,
        )

        next_num = len(block.takes) + 1
        take_id = f"t{next_num:03d}"
        filename = f"{block.id}_{take_id}.wav"
        out_path = self.store.take_path(project.id, filename)

        self.client.synthesize_design(req, out_path)
        duration = ffprobe_duration(out_path)
        take = Take(
            id=take_id,
            file=filename,
            duration=duration,
            input_hash=compute_block_input_hash(block, project),
        )
        block.takes.append(take)
        block.selected_take_id = take.id
        return take

    def export_episode(self, project_id: str, fmt: str = "wav") -> ExportResponse:
        project = self.store.load(project_id)
        entries = []
        for block in project.blocks:
            take = block.selected_take()
            if take is None:
                continue
            wav_path = self.store.take_path(project.id, take.file)
            if wav_path.exists():
                entries.append((wav_path, block.pause_after))

        if not entries:
            raise ValueError("No generated takes available to export.")

        filename = f"{_safe_slug(project.title)}.{fmt}"
        out_path = self.store.export_path(project.id, filename)
        export_project_audio(
            entries,
            out_path=out_path,
            fmt="mp3" if fmt == "mp3" else "wav",
            trim_silence=project.trim_silence,
            normalize_loudness=project.normalize_loudness,
        )
        duration = ffprobe_duration(out_path)
        return ExportResponse(
            file=filename,
            download_url=f"/api/projects/{project.id}/exports/{filename}",
            duration=duration,
            block_count=len(entries),
        )
