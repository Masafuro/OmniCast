"""File-based JSON + WAV storage for OmniCast projects and voices."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from omnicast.characters import DEFAULT_CHARACTERS, CharacterPreset
from omnicast.models import Project, ProjectSummary, VoiceProfile, utc_now_iso

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_RESERVED_VOICE_DIRS = {"_drafts"}


class ProjectNotFoundError(FileNotFoundError):
    """Raised when a requested project does not exist."""


class VoiceNotFoundError(FileNotFoundError):
    """Raised when a requested voice profile does not exist."""


class InvalidIdentifierError(ValueError):
    """Raised when an ID or filename contains unsafe characters."""


def _validate_id(value: str, label: str = "id") -> str:
    if not value or not _SAFE_ID_RE.match(value) or value in _RESERVED_VOICE_DIRS:
        raise InvalidIdentifierError(f"Invalid {label}: {value!r}")
    return value


def _validate_filename(name: str) -> str:
    if not name or Path(name).name != name or ".." in name:
        raise InvalidIdentifierError(f"Invalid filename: {name!r}")
    return name


def _atomic_write_text(target_file: Path, content: str, prefix: str = ".tmp_") -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=target_file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, target_file)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _preset_to_profile(preset: CharacterPreset) -> VoiceProfile:
    return VoiceProfile(
        id=preset.id,
        name=preset.name,
        role=preset.role,
        mode="design",
        is_builtin=True,
        is_customized=False,
        gender=preset.gender,
        age=preset.age,
        pitch=preset.pitch,
        style=preset.style,
        english_accent=preset.english_accent,
        chinese_dialect=preset.chinese_dialect,
    )


class VoiceStore:
    """Manages built-in presets and custom voice profiles under `<data_dir>/voices/`."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.voices_dir = data_dir / "voices"
        self.drafts_dir = self.voices_dir / "_drafts"
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self._builtin_ids = {p.id for p in DEFAULT_CHARACTERS}

    def voice_dir(self, voice_id: str) -> Path:
        return self.voices_dir / _validate_id(voice_id, "voice_id")

    def ref_audio_path(self, voice_id: str) -> Path:
        return self.voice_dir(voice_id) / "ref_audio.wav"

    def draft_path(self, filename: str) -> Path:
        return self.drafts_dir / _validate_filename(filename)

    def delete_draft(self, filename: str) -> bool:
        path = self.draft_path(filename)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _load_custom_profile(self, voice_id: str) -> VoiceProfile | None:
        meta_file = self.voice_dir(voice_id) / "profile.json"
        if not meta_file.exists():
            return None
        profile = VoiceProfile.model_validate_json(meta_file.read_text(encoding="utf-8"))
        profile.is_builtin = voice_id in self._builtin_ids
        profile.is_customized = True
        return profile

    def list_voices(self) -> list[VoiceProfile]:
        result: list[VoiceProfile] = []
        seen_ids: set[str] = set()

        for preset in DEFAULT_CHARACTERS:
            custom = self._load_custom_profile(preset.id)
            result.append(custom if custom is not None else _preset_to_profile(preset))
            seen_ids.add(preset.id)

        custom_extras: list[VoiceProfile] = []
        for entry in self.voices_dir.iterdir():
            if not entry.is_dir() or entry.name in _RESERVED_VOICE_DIRS or entry.name in seen_ids:
                continue
            meta_file = entry / "profile.json"
            if not meta_file.exists():
                continue
            profile = VoiceProfile.model_validate_json(meta_file.read_text(encoding="utf-8"))
            profile.is_builtin = False
            profile.is_customized = True
            custom_extras.append(profile)

        custom_extras.sort(key=lambda v: v.name.lower())
        result.extend(custom_extras)
        return result

    def voices_by_id(self) -> dict[str, VoiceProfile]:
        return {v.id: v for v in self.list_voices()}

    def get(self, voice_id: str) -> VoiceProfile:
        safe_id = _validate_id(voice_id, "voice_id")
        custom = self._load_custom_profile(safe_id)
        if custom is not None:
            return custom
        for preset in DEFAULT_CHARACTERS:
            if preset.id == safe_id:
                return _preset_to_profile(preset)
        raise VoiceNotFoundError(f"Voice not found: {voice_id}")

    def resolve_voice(self, name_or_id: str) -> tuple[VoiceProfile, bool]:
        """Resolve a character by ID or display name (case-insensitive), falling back to Alice."""
        key = name_or_id.strip().lower()
        voices = self.list_voices()
        for voice in voices:
            if voice.id.lower() == key or voice.name.lower() == key:
                return voice, True
        return voices[0], False

    def allocate_voice_id(self, name: str) -> str:
        """Allocate a filesystem/URL-safe unique voice ID for a display name."""
        existing_lower = {v.id.lower() for v in self.list_voices()}
        candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
        if (
            candidate
            and _SAFE_ID_RE.match(candidate)
            and candidate not in _RESERVED_VOICE_DIRS
            and candidate.lower() not in existing_lower
        ):
            return candidate
        return f"v_{uuid.uuid4().hex[:8]}"

    def is_safe_voice_id(self, voice_id: str) -> bool:
        return bool(voice_id and _SAFE_ID_RE.match(voice_id) and voice_id not in _RESERVED_VOICE_DIRS)

    def create(self, profile_data: dict) -> VoiceProfile:
        name = str(profile_data.get("name", "")).strip()
        if not name:
            raise ValueError("Character name is required.")
        for existing in self.list_voices():
            if existing.name.lower() == name.lower():
                raise ValueError(f"Character name already exists: {name}")

        voice_id = self.allocate_voice_id(name)
        profile = VoiceProfile(
            id=voice_id,
            is_builtin=False,
            is_customized=True,
            **profile_data,
        )
        return self.save(profile)

    def save(self, profile: VoiceProfile) -> VoiceProfile:
        vdir = self.voice_dir(profile.id)
        vdir.mkdir(parents=True, exist_ok=True)
        profile.is_builtin = profile.id in self._builtin_ids
        profile.is_customized = True
        profile.updated_at = utc_now_iso()
        _atomic_write_text(vdir / "profile.json", profile.model_dump_json(indent=2), prefix=".voice_")
        return profile

    def delete(self, voice_id: str) -> str:
        """Delete a custom voice, or revert a customized built-in preset to default."""
        vdir = self.voice_dir(voice_id)
        if voice_id in self._builtin_ids:
            if not vdir.exists():
                raise ValueError("Built-in default character cannot be deleted.")
            shutil.rmtree(vdir)
            return "reverted"
        if not vdir.exists():
            raise VoiceNotFoundError(f"Voice not found: {voice_id}")
        shutil.rmtree(vdir)
        return "deleted"


class ProjectStore:
    """Manages project metadata and audio files under `<data_dir>/projects/`."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.projects_dir = data_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        safe_id = _validate_id(project_id, "project_id")
        return self.projects_dir / safe_id

    def takes_dir(self, project_id: str) -> Path:
        path = self.project_dir(project_id) / "takes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def exports_dir(self, project_id: str) -> Path:
        path = self.project_dir(project_id) / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def take_path(self, project_id: str, filename: str) -> Path:
        return self.takes_dir(project_id) / _validate_filename(filename)

    def export_path(self, project_id: str, filename: str) -> Path:
        return self.exports_dir(project_id) / _validate_filename(filename)

    def list_projects(self) -> list[ProjectSummary]:
        summaries: list[ProjectSummary] = []
        for entry in self.projects_dir.iterdir():
            if not entry.is_dir():
                continue
            meta_file = entry / "project.json"
            if not meta_file.exists():
                continue
            project = Project.model_validate_json(meta_file.read_text(encoding="utf-8"))
            summaries.append(
                ProjectSummary(
                    id=project.id,
                    title=project.title,
                    block_count=len(project.blocks),
                    updated_at=project.updated_at,
                )
            )
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    def load(self, project_id: str) -> Project:
        meta_file = self.project_dir(project_id) / "project.json"
        if not meta_file.exists():
            raise ProjectNotFoundError(f"Project not found: {project_id}")
        return Project.model_validate_json(meta_file.read_text(encoding="utf-8"))

    def save(self, project: Project) -> Project:
        pdir = self.project_dir(project.id)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "takes").mkdir(exist_ok=True)
        (pdir / "exports").mkdir(exist_ok=True)

        project.updated_at = utc_now_iso()
        _atomic_write_text(pdir / "project.json", project.model_dump_json(indent=2), prefix=".project_")
        return project

    def delete(self, project_id: str) -> None:
        pdir = self.project_dir(project_id)
        if not pdir.exists():
            raise ProjectNotFoundError(f"Project not found: {project_id}")
        shutil.rmtree(pdir)
