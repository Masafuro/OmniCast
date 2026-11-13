"""Core orchestration service for block synthesis, voice lab previews, and export."""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from omnicast.audio import export_project_audio, ffprobe_duration, normalize_to_wav
from omnicast.models import (
    Block,
    ClonePreviewRequest,
    ClonePreviewResponse,
    DesignPreviewRequest,
    DesignPreviewResponse,
    ExportResponse,
    GenerateBatchResponse,
    Project,
    ProjectView,
    Take,
    VoiceProfile,
    compute_block_input_hash,
)
from omnicast.omnivoice import (
    CloneSynthesisRequest,
    DesignSynthesisRequest,
    OmniVoiceClient,
)
from omnicast.storage import ProjectStore, VoiceStore


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
    """Coordinates TTS synthesis, Cast voice lab operations, and episode audio export."""

    def __init__(
        self,
        store: ProjectStore,
        client: OmniVoiceClient,
        voice_store: VoiceStore | None = None,
    ) -> None:
        self.store = store
        self.voice_store = voice_store or VoiceStore(store.data_dir)
        self.client = client

    def project_view(self, project: Project) -> ProjectView:
        return ProjectView.from_project(project, self.voice_store.voices_by_id())

    def generate_block_take(self, project_id: str, block_id: str) -> ProjectView:
        project = self.store.load(project_id)
        block = _find_block(project, block_id)
        self._synthesize_into_block(project, block)
        self.store.save(project)
        return self.project_view(project)

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
            project=self.project_view(project),
            generated_block_ids=generated_ids,
            skipped_count=skipped,
        )

    def _synthesize_into_block(self, project: Project, block: Block) -> Take:
        tts_text = block.effective_tts_text()
        if not tts_text:
            raise ValueError(f"Block {block.id} has empty text.")

        voice, _ = self.voice_store.resolve_voice(block.voice_id)
        effective_lang = (
            block.lang
            or (voice.lang if voice.lang and voice.lang != "Auto" else None)
            or project.default_lang
            or "Auto"
        )
        effective_speed = block.speed if block.speed is not None else voice.default_speed

        next_num = len(block.takes) + 1
        take_id = f"t{next_num:03d}"
        filename = f"{block.id}_{take_id}.wav"
        out_path = self.store.take_path(project.id, filename)

        ref_path = self.voice_store.ref_audio_path(voice.id)
        if voice.mode == "clone" and voice.ref_audio and ref_path.exists():
            effective_instruct = (
                block.instruct if block.instruct is not None else voice.default_instruct
            )
            clone_req = CloneSynthesisRequest(
                text=tts_text,
                ref_audio_path=ref_path,
                ref_text=voice.ref_text,
                instruct=effective_instruct,
                lang=effective_lang,
                speed=effective_speed,
            )
            self.client.synthesize_clone(clone_req, out_path)
        else:
            design_req = DesignSynthesisRequest(
                text=tts_text,
                lang=effective_lang,
                gender=voice.gender,
                age=voice.age,
                pitch=voice.pitch,
                style=block.style or voice.style,
                english_accent=voice.english_accent,
                chinese_dialect=voice.chinese_dialect,
                speed=effective_speed,
            )
            self.client.synthesize_design(design_req, out_path)

        duration = ffprobe_duration(out_path)
        take = Take(
            id=take_id,
            file=filename,
            duration=duration,
            input_hash=compute_block_input_hash(block, project, voice),
        )
        block.takes.append(take)
        block.selected_take_id = take.id
        return take

    # --- Cast / Voice Lab ---

    def generate_design_preview(self, req: DesignPreviewRequest) -> DesignPreviewResponse:
        filename = f"design_{uuid.uuid4().hex[:10]}.wav"
        out_path = self.voice_store.draft_path(filename)
        self.client.synthesize_design(
            DesignSynthesisRequest(
                text=req.text,
                lang=req.lang,
                gender=req.gender,
                age=req.age,
                pitch=req.pitch,
                style=req.style,
                english_accent=req.english_accent,
                chinese_dialect=req.chinese_dialect,
                speed=req.speed,
            ),
            out_path,
        )
        duration = ffprobe_duration(out_path)
        return DesignPreviewResponse(
            preview_file=filename,
            audio_url=f"/api/voices/drafts/{filename}",
            duration=duration,
        )

    def adopt_preview_as_ref(
        self, voice_id: str, preview_file: str, ref_text: str = ""
    ) -> VoiceProfile:
        voice = self.voice_store.get(voice_id)
        src_path = self.voice_store.draft_path(preview_file)
        if not src_path.exists():
            raise FileNotFoundError(f"Preview file not found: {preview_file}")

        dst_path = self.voice_store.ref_audio_path(voice.id)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

        voice.mode = "clone"
        voice.ref_audio = "ref_audio.wav"
        voice.ref_audio_duration = ffprobe_duration(dst_path)
        voice.ref_text = ref_text
        voice.ref_version += 1
        return self.voice_store.save(voice)

    def set_uploaded_ref_audio(self, voice_id: str, uploaded_path: Path) -> VoiceProfile:
        voice = self.voice_store.get(voice_id)
        dst_path = self.voice_store.ref_audio_path(voice.id)
        normalize_to_wav(uploaded_path, dst_path)

        voice.mode = "clone"
        voice.ref_audio = "ref_audio.wav"
        voice.ref_audio_duration = ffprobe_duration(dst_path)
        voice.ref_version += 1
        return self.voice_store.save(voice)

    def generate_voice_test(
        self, voice_id: str, req: ClonePreviewRequest
    ) -> ClonePreviewResponse:
        voice = self.voice_store.get(voice_id)
        filename = f"test_{voice.id}_{uuid.uuid4().hex[:8]}.wav"
        out_path = self.voice_store.draft_path(filename)
        effective_lang = req.lang or voice.lang or "Auto"
        effective_speed = req.speed if req.speed is not None else voice.default_speed

        ref_path = self.voice_store.ref_audio_path(voice.id)
        if voice.mode == "clone" and voice.ref_audio and ref_path.exists():
            effective_instruct = (
                req.instruct if req.instruct is not None else voice.default_instruct
            )
            self.client.synthesize_clone(
                CloneSynthesisRequest(
                    text=req.text,
                    ref_audio_path=ref_path,
                    ref_text=voice.ref_text,
                    instruct=effective_instruct,
                    lang=effective_lang,
                    speed=effective_speed,
                ),
                out_path,
            )
            mode_used = "clone"
        else:
            self.client.synthesize_design(
                DesignSynthesisRequest(
                    text=req.text,
                    lang=effective_lang,
                    gender=voice.gender,
                    age=voice.age,
                    pitch=voice.pitch,
                    style=voice.style,
                    english_accent=voice.english_accent,
                    chinese_dialect=voice.chinese_dialect,
                    speed=effective_speed,
                ),
                out_path,
            )
            mode_used = "design"

        duration = ffprobe_duration(out_path)
        return ClonePreviewResponse(
            preview_file=filename,
            audio_url=f"/api/voices/drafts/{filename}",
            duration=duration,
            mode_used=mode_used,
        )

    def export_voice_zip(self, voice_id: str) -> tuple[bytes, str]:
        voice = self.voice_store.get(voice_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("profile.json", voice.model_dump_json(indent=2))
            ref_path = self.voice_store.ref_audio_path(voice.id)
            if voice.ref_audio and ref_path.exists():
                zf.write(ref_path, arcname="ref_audio.wav")

        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", voice.name.strip()).strip("_") or voice.id
        return buf.getvalue(), f"{safe_name}.omnicast-voice.zip"

    def import_voice_zip(
        self,
        zip_bytes: bytes,
        conflict: Literal["rename", "overwrite"] = "rename",
    ) -> VoiceProfile:
        if len(zip_bytes) > 50 * 1024 * 1024:
            raise ValueError("Voice archive exceeds 50 MB limit.")

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid ZIP file.") from exc

        with zf:
            members: dict[str, zipfile.ZipInfo] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError(f"Unsafe archive member path: {info.filename!r}")
                members[Path(name).name] = info

            if "profile.json" not in members:
                raise ValueError("Archive does not contain profile.json.")

            try:
                incoming = VoiceProfile.model_validate_json(
                    zf.read(members["profile.json"]).decode("utf-8")
                )
            except Exception as exc:
                raise ValueError(f"Invalid profile.json: {exc}") from exc

            existing_voices = self.voice_store.list_voices()
            by_id = {v.id.lower(): v for v in existing_voices}
            by_name = {v.name.lower(): v for v in existing_voices}

            matched = by_id.get(incoming.id.lower()) or by_name.get(incoming.name.lower())
            if matched and conflict == "overwrite":
                target_id = matched.id
                target_name = matched.name if matched.is_builtin else incoming.name
                next_ref_version = max(matched.ref_version, incoming.ref_version) + 1
            else:
                # Choose unique name if colliding
                target_name = incoming.name.strip() or "Imported Voice"
                if target_name.lower() in by_name:
                    suffix = 2
                    while f"{target_name} ({suffix})".lower() in by_name:
                        suffix += 1
                    target_name = f"{target_name} ({suffix})"

                if (
                    self.voice_store.is_safe_voice_id(incoming.id)
                    and incoming.id.lower() not in by_id
                ):
                    target_id = incoming.id
                else:
                    target_id = self.voice_store.allocate_voice_id(target_name)
                next_ref_version = max(1, incoming.ref_version)

            vdir = self.voice_store.voice_dir(target_id)
            vdir.mkdir(parents=True, exist_ok=True)
            dst_ref = self.voice_store.ref_audio_path(target_id)

            if "ref_audio.wav" in members:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                    tmp.write(zf.read(members["ref_audio.wav"]))
                try:
                    normalize_to_wav(tmp_path, dst_ref)
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink()
                ref_audio_name: str | None = "ref_audio.wav"
                ref_duration: float | None = ffprobe_duration(dst_ref)
                mode = incoming.mode if incoming.mode in {"clone", "design"} else "clone"
            else:
                if dst_ref.exists():
                    dst_ref.unlink()
                ref_audio_name = None
                ref_duration = None
                mode = "design"

            imported = VoiceProfile(
                id=target_id,
                name=target_name,
                role=incoming.role,
                mode=mode,
                lang=incoming.lang,
                default_speed=incoming.default_speed,
                default_instruct=incoming.default_instruct,
                ref_audio=ref_audio_name,
                ref_audio_duration=ref_duration,
                ref_text=incoming.ref_text,
                ref_version=next_ref_version if ref_audio_name else 0,
                gender=incoming.gender,
                age=incoming.age,
                pitch=incoming.pitch,
                style=incoming.style,
                english_accent=incoming.english_accent,
                chinese_dialect=incoming.chinese_dialect,
            )
            return self.voice_store.save(imported)

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
