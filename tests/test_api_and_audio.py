"""End-to-end API, take management, locking, and ffmpeg export tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from omnicast.app import create_app
from omnicast.audio import ffprobe_duration
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


def test_health_characters_and_static_ui(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["omnivoice"]["mode"] == "mock"

    chars = client.get("/api/characters").json()
    assert [c["id"] for c in chars] == ["Alice", "Bob", "Carol", "Dave", "Narrator"]

    assert client.get("/").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200


def test_full_studio_workflow_retake_lock_and_export(tmp_path: Path) -> None:
    client, mock_ov = make_client(tmp_path)

    # 1. Create project and import script
    proj = client.post(
        "/api/projects",
        json={"title": "Test Episode", "default_lang": "Japanese", "default_turn_pause": 0.4},
    ).json()
    pid = proj["id"]

    imp = client.post(
        f"/api/projects/{pid}/import-script",
        json={"script": "@Alice: おはようございます。\n@Bob: おはよう！今日も始めよう。", "mode": "replace"},
    )
    assert imp.status_code == 200
    blocks = imp.json()["project"]["blocks"]
    assert len(blocks) == 2
    assert all(b["status"] == "unbuilt" for b in blocks)
    b0_id, b1_id = blocks[0]["id"], blocks[1]["id"]

    # 2. Batch generate
    gen = client.post(f"/api/projects/{pid}/generate")
    assert gen.status_code == 200
    assert gen.json()["generated_block_ids"] == [b0_id, b1_id]
    assert len(mock_ov.calls) == 2

    # 3. Retake block 0 -> 2 takes, then switch back to t001
    retake = client.post(f"/api/projects/{pid}/blocks/{b0_id}/generate").json()
    b0 = retake["blocks"][0]
    assert len(b0["takes"]) == 2
    assert b0["selected_take_id"] == "t002"

    switched = client.patch(
        f"/api/projects/{pid}/blocks/{b0_id}",
        json={"selected_take_id": "t001"},
    ).json()
    assert switched["blocks"][0]["selected_take_id"] == "t001"

    # 4. Lock block 0 and edit both blocks; batch generate only regenerates unlocked block 1
    client.patch(f"/api/projects/{pid}/blocks/{b0_id}", json={"locked": True, "text": "表記だけ変更"})
    edited = client.patch(
        f"/api/projects/{pid}/blocks/{b1_id}",
        json={"text": "編集後のセリフです！"},
    ).json()
    assert edited["blocks"][0]["status"] == "locked"
    assert edited["blocks"][1]["status"] == "dirty"

    calls_before = len(mock_ov.calls)
    gen2 = client.post(f"/api/projects/{pid}/generate").json()
    assert gen2["generated_block_ids"] == [b1_id]
    assert gen2["skipped_count"] == 1
    assert len(mock_ov.calls) == calls_before + 1

    # 4b. Running batch generate again regenerates unlocked 'ready' block 1 too, while locked block 0 stays skipped
    gen3 = client.post(f"/api/projects/{pid}/generate").json()
    assert gen3["generated_block_ids"] == [b1_id]
    assert gen3["skipped_count"] == 1
    assert len(gen3["project"]["blocks"][1]["takes"]) == 3

    # 5. Reorder blocks, insert new block, delete it, adjust pause, and export WAV & MP3
    reordered = client.post(
        f"/api/projects/{pid}/blocks/reorder",
        json={"block_ids": [b1_id, b0_id]},
    ).json()
    assert [b["id"] for b in reordered["blocks"]] == [b1_id, b0_id]

    added = client.post(
        f"/api/projects/{pid}/blocks",
        json={"voice_id": "Carol", "text": "挿入テスト", "insert_index": 1},
    ).json()
    assert len(added["blocks"]) == 3
    inserted_id = added["blocks"][1]["id"]
    client.delete(f"/api/projects/{pid}/blocks/{inserted_id}")

    client.patch(f"/api/projects/{pid}/blocks/{b1_id}", json={"pause_after": 0.8})

    for fmt in ("wav", "mp3"):
        exp = client.post(f"/api/projects/{pid}/export", json={"format": fmt})
        assert exp.status_code == 200
        exp_data = exp.json()
        assert exp_data["block_count"] == 2
        assert exp_data["duration"] > 1.0

        dl = client.get(exp_data["download_url"])
        assert dl.status_code == 200
        assert len(dl.content) > 1000

        saved = tmp_path / "projects" / pid / "exports" / exp_data["file"]
        assert ffprobe_duration(saved) > 1.0
