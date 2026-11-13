"""OmniVoice client abstraction with Gradio and offline Mock implementations."""

from __future__ import annotations

import hashlib
import math
import shutil
import struct
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class DesignSynthesisRequest:
    """Parameters passed to OmniVoice `/_design_fn`."""

    text: str
    lang: str = "Auto"
    gender: str = "Auto"
    age: str = "Auto"
    pitch: str = "Auto"
    style: str = "Auto"
    english_accent: str = "Auto"
    chinese_dialect: str = "Auto"
    speed: float = 1.0
    ns: float = 32.0
    gs: float = 2.0
    dn: bool = True
    pp: bool = True
    po: bool = True


@dataclass(frozen=True)
class CloneSynthesisRequest:
    """Parameters passed to OmniVoice `/_clone_fn`."""

    text: str
    ref_audio_path: Path
    ref_text: str = ""
    instruct: str = ""
    lang: str = "Auto"
    speed: float = 1.0
    ns: float = 32.0
    gs: float = 2.0
    dn: bool = True
    pp: bool = True
    po: bool = True


class OmniVoiceError(RuntimeError):
    """Raised when OmniVoice synthesis fails."""


class OmniVoiceClient(Protocol):
    """Protocol for TTS generation backends."""

    @property
    def mode(self) -> str: ...

    def synthesize_design(self, request: DesignSynthesisRequest, out_path: Path) -> Path: ...

    def synthesize_clone(self, request: CloneSynthesisRequest, out_path: Path) -> Path: ...

    def health_check(self) -> dict[str, Any]: ...


class GradioOmniVoiceClient:
    """Client calling k2-fsa/OmniVoice Gradio Web UI (`/_design_fn` and `/_clone_fn`)."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self._lock = threading.Lock()
        self._client: Any | None = None

    @property
    def mode(self) -> str:
        return "gradio"

    def _get_client(self) -> Any:
        if self._client is None:
            from gradio_client import Client

            self._client = Client(self.url)
        return self._client

    def _copy_result(self, result: Any, out_path: Path) -> Path:
        if not result or not result[0]:
            raise OmniVoiceError(f"OmniVoice returned empty audio: {result!r}")
        src_path = Path(result[0])
        if not src_path.exists():
            raise OmniVoiceError(f"OmniVoice output file not found: {src_path}")
        shutil.copy2(src_path, out_path)
        return out_path

    def synthesize_design(self, request: DesignSynthesisRequest, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            try:
                client = self._get_client()
                result = client.predict(
                    text=request.text,
                    lang=request.lang,
                    ns=request.ns,
                    gs=request.gs,
                    dn=request.dn,
                    sp=request.speed,
                    du=0,
                    pp=request.pp,
                    po=request.po,
                    param_9=request.gender,
                    param_10=request.age,
                    param_11=request.pitch,
                    param_12=request.style,
                    param_13=request.english_accent,
                    param_14=request.chinese_dialect,
                    api_name="/_design_fn",
                )
            except Exception as exc:
                self._client = None
                raise OmniVoiceError(f"OmniVoice design request failed: {exc}") from exc

        return self._copy_result(result, out_path)

    def synthesize_clone(self, request: CloneSynthesisRequest, out_path: Path) -> Path:
        if not request.ref_audio_path.exists():
            raise OmniVoiceError(f"Reference audio not found: {request.ref_audio_path}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            try:
                from gradio_client import handle_file

                client = self._get_client()
                result = client.predict(
                    text=request.text,
                    lang=request.lang,
                    ref_aud=handle_file(str(request.ref_audio_path)),
                    ref_text=request.ref_text,
                    instruct=request.instruct,
                    ns=request.ns,
                    gs=request.gs,
                    dn=request.dn,
                    sp=request.speed,
                    du=0,
                    pp=request.pp,
                    po=request.po,
                    api_name="/_clone_fn",
                )
            except Exception as exc:
                self._client = None
                raise OmniVoiceError(f"OmniVoice clone request failed: {exc}") from exc

        return self._copy_result(result, out_path)

    def health_check(self) -> dict[str, Any]:
        return {"mode": self.mode, "url": self.url, "ok": True}


class MockOmniVoiceClient:
    """Offline synthetic WAV generator for tests and UI development without a GPU."""

    def __init__(self, sample_rate: int = 24000) -> None:
        self.sample_rate = sample_rate
        self.calls: list[DesignSynthesisRequest] = []
        self.clone_calls: list[CloneSynthesisRequest] = []

    @property
    def mode(self) -> str:
        return "mock"

    def _write_tone_wav(self, out_path: Path, freq: float, duration: float) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n_samples = int(self.sample_rate * duration)
        fade_samples = min(int(self.sample_rate * 0.02), n_samples // 4)
        frames = bytearray()
        for i in range(n_samples):
            env = 1.0
            if fade_samples > 0:
                if i < fade_samples:
                    env = i / fade_samples
                elif i > n_samples - fade_samples:
                    env = (n_samples - i) / fade_samples
            val = int(9000 * env * math.sin(2.0 * math.pi * freq * (i / self.sample_rate)))
            frames.extend(struct.pack("<h", val))

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(bytes(frames))
        return out_path

    def synthesize_design(self, request: DesignSynthesisRequest, out_path: Path) -> Path:
        self.calls.append(request)

        base_freq = 220.0 if "Female" in request.gender else 135.0
        if "Very Low" in request.pitch:
            base_freq *= 0.8
        elif "Low" in request.pitch:
            base_freq *= 0.9
        elif "High" in request.pitch:
            base_freq *= 1.15

        digest = hashlib.sha256(f"{request.text}:{len(self.calls)}".encode("utf-8")).digest()
        freq = base_freq + (digest[0] % 25)
        duration = max(0.5, min(6.0, len(request.text) * 0.08 / max(request.speed, 0.5)))
        return self._write_tone_wav(out_path, freq=freq, duration=duration)

    def synthesize_clone(self, request: CloneSynthesisRequest, out_path: Path) -> Path:
        if not request.ref_audio_path.exists():
            raise OmniVoiceError(f"Reference audio not found: {request.ref_audio_path}")
        self.clone_calls.append(request)

        ref_digest = hashlib.sha256(request.ref_audio_path.read_bytes()[:4096]).digest()
        base_freq = 160.0 + (ref_digest[0] % 90)
        duration = max(0.5, min(6.0, len(request.text) * 0.08 / max(request.speed, 0.5)))
        return self._write_tone_wav(out_path, freq=base_freq, duration=duration)

    def health_check(self) -> dict[str, Any]:
        return {"mode": self.mode, "url": None, "ok": True}
