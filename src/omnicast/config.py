"""Application configuration loaded from environment and optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(env_path: Path) -> None:
    """Populate os.environ from a .env file without overriding existing values."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    """Runtime settings for OmniCast."""

    omnivoice_url: str
    data_dir: Path
    host: str
    port: int
    use_mock: bool = False

    @classmethod
    def from_env(cls, root_dir: Path | None = None) -> Settings:
        base = root_dir or Path.cwd()
        load_dotenv(base / ".env")
        data_raw = os.environ.get("OMNICAST_DATA_DIR", "./data")
        data_path = Path(data_raw)
        if not data_path.is_absolute():
            data_path = (base / data_path).resolve()

        return cls(
            omnivoice_url=os.environ.get("OMNIVOICE_URL", "http://127.0.0.1:8000").rstrip("/"),
            data_dir=data_path,
            host=os.environ.get("OMNICAST_HOST", "0.0.0.0"),
            port=int(os.environ.get("OMNICAST_PORT", "8080")),
            use_mock=os.environ.get("OMNICAST_MOCK", "").lower() in {"1", "true", "yes"},
        )
