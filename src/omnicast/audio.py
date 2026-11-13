"""Audio inspection and ffmpeg stitching/export helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

SAMPLE_RATE = 24000


class AudioProcessingError(RuntimeError):
    """Raised when ffprobe or ffmpeg fails."""


def ffprobe_duration(path: Path) -> float:
    """Measure audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise AudioProcessingError(f"ffprobe failed for {path}: {res.stderr.strip()}")
    try:
        return round(float(res.stdout.strip()), 3)
    except ValueError as exc:
        raise AudioProcessingError(f"Unexpected ffprobe duration output: {res.stdout!r}") from exc


def export_project_audio(
    take_entries: list[tuple[Path, float]],
    out_path: Path,
    fmt: Literal["wav", "mp3"] = "wav",
    trim_silence: bool = True,
    normalize_loudness: bool = True,
) -> Path:
    """Concatenate take WAVs with pauses, optional edge-silence trim, and normalization."""
    if not take_entries:
        raise AudioProcessingError("No generated takes available to export.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filter_parts: list[str] = []
    concat_labels: list[str] = []

    for idx, (wav_path, pause_sec) in enumerate(take_entries):
        if not wav_path.exists():
            raise AudioProcessingError(f"Take audio file is missing: {wav_path}")
        inputs.extend(["-i", str(wav_path)])

        chain = [f"aresample={SAMPLE_RATE}", "aformat=channel_layouts=mono"]
        if trim_silence:
            # Trim only outer leading/trailing silence while keeping 40ms edge margin.
            chain.extend(
                [
                    "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB",
                    "areverse",
                    "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB",
                    "areverse",
                ]
            )
        chain.append("afade=t=in:d=0.01")
        label = f"[seg{idx}]"
        filter_parts.append(f"[{idx}:a]{','.join(chain)}{label}")
        concat_labels.append(label)

        if idx < len(take_entries) - 1 and pause_sec > 0.005:
            sil_label = f"[sil{idx}]"
            filter_parts.append(f"anullsrc=r={SAMPLE_RATE}:cl=mono:d={pause_sec:.3f}{sil_label}")
            concat_labels.append(sil_label)

    total_streams = len(concat_labels)
    if normalize_loudness:
        filter_parts.append(f"{''.join(concat_labels)}concat=n={total_streams}:v=0:a=1[joined]")
        filter_parts.append("[joined]loudnorm=I=-16:TP=-1.5:LRA=11[out]")
    else:
        filter_parts.append(f"{''.join(concat_labels)}concat=n={total_streams}:v=0:a=1[out]")

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[out]",
    ]
    if fmt == "mp3":
        cmd.extend(["-codec:a", "libmp3lame", "-q:a", "2"])
    else:
        cmd.extend(["-codec:a", "pcm_s16le"])
    cmd.append(str(out_path))

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise AudioProcessingError(f"ffmpeg export failed: {res.stderr.strip()}")

    return out_path
