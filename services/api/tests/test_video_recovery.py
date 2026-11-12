import subprocess

import pytest
from sqlalchemy import select

from haytile import providers, storage, video, worker
from haytile.db import Job, Ledger, Session
from haytile.providers import ProviderError
from haytile.video_checkpoints import safe_to_resume

from .conftest import register
from .test_core import configure, fund, job_request
from .test_video import clip


@pytest.mark.parametrize("streamed", [False, True])
def test_failed_assembly_reuses_paid_scenes_without_provider_calls(client, monkeypatch, tmp_path, streamed):
    configure(monkeypatch, "video", 5)
    user, auth = register(client)
    fund(user["id"], 100)
    body = {**job_request("video", 10), "params": {"duration": 16, "aspect": "16:9"}}
    created = client.post("/v1/jobs", headers=auth, json=body)
    assert created.status_code == 202, created.text
    jid = created.json()["id"]
    media = clip(tmp_path / "native.mp4", "blue", 8)
    calls = []

    def generate(studio, model, prompt, params):
        calls.append(params["_scene_index"])
        params["_operation_callback"]("paid-scene-" + str(params["_scene_index"]))
        return (tmp_path / "native.mp4") if streamed else media, "video/mp4"

    original = video.assemble
    monkeypatch.setattr(providers, "generate", generate)
    monkeypatch.setattr(
        video,
        "assemble",
        lambda *a, **kw: (_ for _ in ()).throw(ProviderError("VIDEO_FINAL_DURATION_FAILED")),
    )
    assert worker.run_once()
    with Session() as db:
        row = db.get(Job, jid)
        assert row.status == "failed"
        assert safe_to_resume(row.params)
        saved = row.params["video_checkpoints"]
        assert len(saved) == 2 and all(
            s.get("key") and s.get("operation_id") for s in saved.values()
        )
        assert all(storage.get(s["key"]) == media for s in saved.values())
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 100
    assert calls == [0, 1]
    monkeypatch.setattr(video, "assemble", original)
    monkeypatch.setattr(
        providers, "generate", lambda *a, **kw: pytest.fail("A paid scene must not be regenerated")
    )
    assert client.post("/v1/jobs/" + jid + "/retry", headers=auth).status_code == 200
    assert worker.run_once()
    with Session() as db:
        row = db.get(Job, jid)
        assert row.status == "completed", row.error
        assert row.params["video_checkpoint_cleanup_scheduled"]
        assert (
            len(
                list(db.scalars(select(Ledger).where(Ledger.job_id == jid, Ledger.kind == "debit")))
            )
            == 1
        )
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 90


def test_uncertain_submission_and_legacy_paid_video_cannot_retry_blindly(client, monkeypatch):
    configure(monkeypatch, "video", 5)
    user, auth = register(client)
    fund(user["id"], 100)
    created = client.post(
        "/v1/jobs", headers=auth, json={**job_request("video", 10), "params": {"duration": 16}}
    )
    jid = created.json()["id"]
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *a, **kw: (_ for _ in ()).throw(ProviderError("PROVIDER_NETWORK_OR_RESPONSE")),
    )
    assert worker.run_once()
    with Session() as db:
        row = db.get(Job, jid)
        assert row.status == "failed" and not safe_to_resume(row.params)
    denied = client.post("/v1/jobs/" + jid + "/retry", headers=auth)
    assert denied.status_code == 409 and denied.json()["detail"] == "MANUAL_RECONCILIATION_REQUIRED"
    with Session.begin() as db:
        row = db.get(Job, jid)
        row.params = {**row.params, "video_checkpoint_version": 0, "completed_scenes": 2}
        row.error = "VIDEO_FINAL_DURATION_FAILED"
    assert client.post("/v1/jobs/" + jid + "/retry", headers=auth).status_code == 409
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 100


def test_native_packet_copy_duration_falls_back_without_relaxing_quality(tmp_path, monkeypatch):
    source = tmp_path / "native.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=1280x720:r=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "9",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    original = video.probe
    final_checks = []

    def probe(path):
        info = original(path)
        if path.name == "final.mp4":
            final_checks.append(info)
            if len(final_checks) == 1:
                # Model the out-of-bound packet-copy duration seen in the incident.
                info["format"]["duration"] = "8.25"
        return info

    monkeypatch.setattr(video, "probe", probe)
    result = video.assemble([source], 8)
    output = tmp_path / "result.mp4"
    output.write_bytes(result)
    checked = original(output)
    assert len(final_checks) == 2
    assert abs(float(checked["format"]["duration"]) - 8) <= 0.15
    track = next(s for s in checked["streams"] if s["codec_type"] == "video")
    assert abs(float(track["duration"]) - 8) <= 0.15
    assert int(track["nb_frames"]) == 192
