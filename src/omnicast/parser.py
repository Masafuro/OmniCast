"""Line-oriented `@Name: text` script parser and exporter for OmniCast rev1."""

from __future__ import annotations

import re

from omnicast.characters import FALLBACK_CHARACTER, resolve_character
from omnicast.models import Block, Project

# Matches `@SpeakerName: optional initial text`
_SPEAKER_LINE_RE = re.compile(r"^\s*@([^:\s][^:]*?)\s*:\s*(.*)$")


def parse_script(script_text: str, default_pause: float = 0.45) -> tuple[list[Block], list[str]]:
    """Parse `@Name: text` script lines into Block objects plus warning strings."""
    blocks: list[Block] = []
    warnings: list[str] = []
    warned_unknown: set[str] = set()

    current_voice: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_voice, current_lines
        if current_voice is None:
            return
        body = "\n".join(current_lines).strip()
        if body:
            blocks.append(
                Block(
                    voice_id=current_voice,
                    text=body,
                    pause_after=default_pause,
                )
            )
        current_voice = None
        current_lines = []

    for line_no, raw_line in enumerate(script_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            continue

        match = _SPEAKER_LINE_RE.match(raw_line)
        if match:
            flush_current()
            raw_speaker, first_text = match.group(1), match.group(2)
            preset, matched = resolve_character(raw_speaker)
            if not matched and raw_speaker.strip() not in warned_unknown:
                warned_unknown.add(raw_speaker.strip())
                warnings.append(
                    f"Line {line_no}: unknown speaker '@{raw_speaker.strip()}' mapped to '{FALLBACK_CHARACTER.id}'."
                )
            current_voice = preset.id
            current_lines = [first_text.strip()] if first_text.strip() else []
            continue

        if not stripped:
            # Preserve internal paragraph breaks only if we already have text
            if current_lines and current_lines[-1] != "":
                current_lines.append("")
            continue

        if current_voice is None:
            warnings.append(
                f"Line {line_no}: text before any @Speaker line assigned to '{FALLBACK_CHARACTER.id}'."
            )
            current_voice = FALLBACK_CHARACTER.id
            current_lines = [stripped]
        else:
            current_lines.append(stripped)

    flush_current()
    return blocks, warnings


def export_script(project: Project) -> str:
    """Serialize a Project's blocks back into `@Name: text` script format."""
    chunks: list[str] = []
    for block in project.blocks:
        text = block.text.strip()
        if not text:
            continue
        lines = text.splitlines()
        first = f"@{block.voice_id}: {lines[0]}"
        if len(lines) > 1:
            chunks.append("\n".join([first, *lines[1:]]))
        else:
            chunks.append(first)
    return "\n\n".join(chunks) + ("\n" if chunks else "")
