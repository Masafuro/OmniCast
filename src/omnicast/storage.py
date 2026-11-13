"""File-based JSON + WAV storage for OmniCast projects."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from omnicast.models import Project, ProjectSummary, utc_now_iso

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ProjectNotFoundError(FileNotFoundError):
    """Raised when a requested project does not exist."""


class InvalidIdentifierError(ValueError):
    """Raised when a project ID or filename contains unsafe characters."""


def _validate_id(value: str, label: str = "id") -> str:
    if not value or not _SAFE_ID_RE.match(value):
        raise InvalidIdentifierError(f"Invalid {label}: {value!r}")
    return value


def _validate_filename(name: str) -> str:
    if not name or Path(name).name != name or ".." in name:
        raise InvalidIdentifierError(f"Invalid filename: {name!r}")
    return name


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
        meta_file = pdir / "project.json"
        content = project.model_dump_json(indent=2)

        fd, tmp_name = tempfile.mkstemp(prefix=".project_", suffix=".json", dir=pdir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_name, meta_file)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
        return project

    def delete(self, project_id: str) -> None:
        pdir = self.project_dir(project_id)
        if not pdir.exists():
            raise ProjectNotFoundError(f"Project not found: {project_id}")
        shutil.rmtree(pdir)
