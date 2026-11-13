"""Tests for rev2 Cast (VoiceProfile), Design Lab, ref audio upload, and Clone synthesis."""

from __future__ import annotations

import io
import json
import math
import struct
import wave
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from omnicast.app import create_app
from omnicast.config import Settings
from omnicast.omnivoice import MockOmniVoiceClient


def make_client(tmp_path: Path) -> tuple[TestClient, MockOmniVoiceClient]:
    mock_ov = MockOmniVoiceClient()
    settings = Settings(
        omnivoice_url="http://127.0.0.1:8000",
        data_dir=tmp_path,
        host="127.0.0.1",
        port=8080,
        use_mock=True,
    )
    app = create_app(settings=settings, client=mock_ov)
    return TestClient(app), mock_ov


def make_wav_bytes(duration_sec: float = 0.6, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    n_samples = int(duration_sec * sample_rate)
    frames = bytearray()
    for i in range(n_samples):
        val = int(8000 * math.sin(2.0 * math.pi * 330.0 * (i / sample_rate)))
        frames.extend(struct.pack("<h", val))
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def test_custom_japanese_character_design_adopt_and_clone_flow(tmp_path: Path) -> None:
    client, mock_ov = make_client(tmp_path)

    # Options & default voices
    opts = client.get("/api/voices/options")
    assert opts.status_code == 200
    assert "Female / 女" in opts.json()["gender"]

    voices = client.get("/api/voices").json()
    assert len(voices) == 5

    # Create a custom Japanese-named character
    created = client.post(
        "/api/voices",
        json={"name": "ミカ", "role": "元気なゲスト", "lang": "Japanese"},
    )
    assert created.status_code == 201
    mika = created.json()
    mika_id = mika["id"]
    assert mika["mode"] == "design"
    assert mika["is_builtin"] is False

    # Generate a Design preview and adopt it as Mika's base voice
    prev = client.post(
        "/api/voices/design-preview",
        json={
            "text": "こんにちは、ミカです。",
            "lang": "Japanese",
            "gender": "Female / 女",
            "age": "Teenager / 少年",
            "pitch": "High Pitch / 高音调",
        },
    )
    assert prev.status_code == 200
    prev_data = prev.json()
    assert client.get(prev_data["audio_url"]).status_code == 200

    adopted = client.post(
        f"/api/voices/{mika_id}/adopt-preview",
        json={"preview_file": prev_data["preview_file"], "ref_text": ""},
    )
    assert adopted.status_code == 200
    assert adopted.json()["mode"] == "clone"
    assert adopted.json()["ref_version"] == 1
    assert client.get(f"/api/voices/{mika_id}/ref-audio").status_code == 200

    # Clone preview test speech
    cp = client.post(
        f"/api/voices/{mika_id}/clone-preview",
        json={"text": "テスト発話です。", "instruct": "明るく"},
    )
    assert cp.status_code == 200
    assert cp.json()["mode_used"] == "clone"
    assert len(mock_ov.clone_calls) == 1
    assert mock_ov.clone_calls[0].instruct == "明るく"

    # Import a script using @ミカ: and generate in Studio -> triggers synthesize_clone
    proj = client.post("/api/projects", json={"title": "Cast Demo"}).json()
    pid = proj["id"]
    imp = client.post(
        f"/api/projects/{pid}/import-script",
        json={"script": "@ミカ: 今日はよろしくお願いします！\n@Alice: こちらこそ！", "mode": "replace"},
    ).json()
    assert imp["warnings"] == []
    blocks = imp["project"]["blocks"]
    assert blocks[0]["voice_id"] == mika_id
    assert blocks[1]["voice_id"] == "Alice"

    clone_calls_before = len(mock_ov.clone_calls)
    design_calls_before = len(mock_ov.calls)
    gen = client.post(f"/api/projects/{pid}/generate")
    assert gen.status_code == 200
    assert len(mock_ov.clone_calls) == clone_calls_before + 1
    assert len(mock_ov.calls) == design_calls_before + 1

    # Script export uses display name "ミカ"
    exported_txt = client.get(f"/api/projects/{pid}/export-script").text
    assert "@ミカ: 今日はよろしくお願いします！" in exported_txt

    # Delete custom character
    deleted = client.delete(f"/api/voices/{mika_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_upload_ref_audio_to_builtin_and_revert(tmp_path: Path) -> None:
    client, mock_ov = make_client(tmp_path)

    # Create project and generate Alice in Design mode first
    proj = client.post("/api/projects", json={"title": "Revert Demo"}).json()
    pid = proj["id"]
    client.post(
        f"/api/projects/{pid}/import-script",
        json={"script": "@Alice: 最初のテストです。", "mode": "replace"},
    )
    client.post(f"/api/projects/{pid}/generate")
    assert client.get(f"/api/projects/{pid}").json()["blocks"][0]["status"] == "ready"

    # Upload custom WAV to built-in Alice -> upgrades Alice to Clone and marks block dirty
    wav_bytes = make_wav_bytes()
    up = client.post(
        "/api/voices/Alice/ref-audio",
        files={"file": ("alice_custom.wav", wav_bytes, "audio/wav")},
    )
    assert up.status_code == 200
    assert up.json()["mode"] == "clone"
    assert up.json()["is_customized"] is True
    assert client.get(f"/api/projects/{pid}").json()["blocks"][0]["status"] == "dirty"

    # Regenerating uses clone
    before_clone = len(mock_ov.clone_calls)
    client.post(f"/api/projects/{pid}/generate")
    assert len(mock_ov.clone_calls) == before_clone + 1

    # Revert Alice back to built-in preset
    rev = client.delete("/api/voices/Alice")
    assert rev.status_code == 200
    assert rev.json()["status"] == "reverted"
    alice = client.get("/api/voices/Alice").json()
    assert alice["mode"] == "design"
    assert alice["is_customized"] is False


def test_export_import_clone_voice_roundtrip_and_rename_conflict(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    # Create a custom Clone character with Japanese name and upload ref audio
    created = client.post(
        "/api/voices",
        json={"name": "ミカ", "role": "ゲスト", "lang": "Japanese", "default_instruct": "明るく"},
    ).json()
    mika_id = created["id"]
    wav_bytes = make_wav_bytes(0.7)
    up = client.post(
        f"/api/voices/{mika_id}/ref-audio",
        files={"file": ("mika_ref.wav", wav_bytes, "audio/wav")},
    )
    assert up.status_code == 200
    assert up.json()["mode"] == "clone"

    # Export ZIP
    exp = client.get(f"/api/voices/{mika_id}/export")
    assert exp.status_code == 200
    assert exp.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''" in exp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(exp.content), "r") as zf:
        names = set(zf.namelist())
        assert names == {"profile.json", "ref_audio.wav"}
        exported_profile = json.loads(zf.read("profile.json").decode("utf-8"))
        assert exported_profile["name"] == "ミカ"
        assert exported_profile["mode"] == "clone"

    # Delete original, then import back -> restores Clone voice with ref_audio
    assert client.delete(f"/api/voices/{mika_id}").status_code == 200
    imp1 = client.post(
        "/api/voices/import",
        files={"file": ("mika.omnicast-voice.zip", exp.content, "application/zip")},
        data={"conflict": "rename"},
    )
    assert imp1.status_code == 200
    restored = imp1.json()
    assert restored["id"] == mika_id
    assert restored["name"] == "ミカ"
    assert restored["mode"] == "clone"
    assert restored["ref_audio"] == "ref_audio.wav"
    assert restored["ref_audio_duration"] is not None and restored["ref_audio_duration"] > 0
    ref_dl = client.get(f"/api/voices/{mika_id}/ref-audio")
    assert ref_dl.status_code == 200
    assert len(ref_dl.content) > 44

    # Duplicate import with conflict="rename" allocates distinct ID and "(2)" name
    imp2 = client.post(
        "/api/voices/import",
        files={"file": ("mika.omnicast-voice.zip", exp.content, "application/zip")},
        data={"conflict": "rename"},
    )
    assert imp2.status_code == 200
    dup = imp2.json()
    assert dup["id"] != mika_id
    assert dup["name"] == "ミカ (2)"
    assert dup["mode"] == "clone"


def test_import_overwrite_upgrades_builtin_and_invalid_zip_returns_400(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    # Export a Clone voice, then craft a package targeting Alice by id
    created = client.post("/api/voices", json={"name": "AliceClone"}).json()
    cid = created["id"]
    client.post(
        f"/api/voices/{cid}/ref-audio",
        files={"file": ("ref.wav", make_wav_bytes(), "audio/wav")},
    )
    exp_bytes = client.get(f"/api/voices/{cid}/export").content

    # Rewrite profile.json inside zip to id="Alice", name="Alice"
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(exp_bytes), "r") as zin, zipfile.ZipFile(buf, "w") as zout:
        prof = json.loads(zin.read("profile.json").decode("utf-8"))
        prof["id"] = "Alice"
        prof["name"] = "Alice"
        prof["role"] = "上書きホスト"
        zout.writestr("profile.json", json.dumps(prof, ensure_ascii=False))
        zout.writestr("ref_audio.wav", zin.read("ref_audio.wav"))

    imp = client.post(
        "/api/voices/import",
        files={"file": ("alice.omnicast-voice.zip", buf.getvalue(), "application/zip")},
        data={"conflict": "overwrite"},
    )
    assert imp.status_code == 200
    alice = imp.json()
    assert alice["id"] == "Alice"
    assert alice["is_builtin"] is True
    assert alice["is_customized"] is True
    assert alice["mode"] == "clone"
    assert alice["role"] == "上書きホスト"

    # Invalid ZIP bytes return HTTP 400
    bad = client.post(
        "/api/voices/import",
        files={"file": ("bad.zip", b"not a zip archive", "application/zip")},
    )
    assert bad.status_code == 400


def test_delete_design_preview_draft(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    prev = client.post(
        "/api/voices/design-preview",
        json={"text": "不要な試作音声です。", "lang": "Japanese"},
    )
    assert prev.status_code == 200
    filename = prev.json()["preview_file"]

    assert client.get(f"/api/voices/drafts/{filename}").status_code == 200
    deleted = client.delete(f"/api/voices/drafts/{filename}")
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "filename": filename}

    assert client.get(f"/api/voices/drafts/{filename}").status_code == 404
    assert client.delete(f"/api/voices/drafts/{filename}").status_code == 404
    assert client.delete("/api/voices/drafts/bad..wav").status_code == 400
