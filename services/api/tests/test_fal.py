"""All fal requests are intercepted; never use an actual account or inference key."""

import copy
import io
import json

import httpx
import pytest

from haytile import fal_catalog, fal_client, fal_inputs, providers, storage, worker
from haytile.db import Asset, Job, Session, User
from haytile.provider_errors import ProviderError

from .conftest import register
from .test_core import configure, fund


def profile(adapter="ace_music", studio=None):
    item = copy.deepcopy(
        next(
            p
            for p in fal_catalog.DEFAULTS
            if p["adapter"] == adapter and (not studio or p["studio"] == studio)
        )
    )
    units = {
        "ace_music": ("0.0002", "seconds"),
        "minimax_music": ("0.15", "audios"),
        "image": ("0.003", "megapixels"),
        "background": ("0.018", "generations"),
        "upscale": ("0.03", "megapixels"),
        "image_edit": ("0.04", "images"),
        "voice": ("0.02", "1000 characters"),
        "text": ("0.001", "requests"),
        "kling_video": ("0.07", "seconds"),
        "wan_video": ("0.08", "seconds"),
        "kling_audio": ("0.14", "seconds"),
        "kling_image_audio": ("0.14", "seconds"),
    }
    rate, unit = units[adapter]
    item.update(
        enabled=True,
        price_verified=True,
        unit_price=rate,
        price_unit=unit,
        allow_paused_studio=True,
    )
    return item


def approve(user_id, item, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "offline-fal-key")
    monkeypatch.setenv("HAYTILE_OPERATOR_BILLING_ACK", "1")
    fal_catalog.invalidate()
    fal_catalog.save(item, user_id)


def test_fal_music_worker_preserves_lyrics_private_result_and_single_debit(client, monkeypatch):
    configure(monkeypatch, "music", 32)
    user, auth = register(client)
    fund(user["id"], 100)
    item = profile()
    approve(user["id"], item, monkeypatch)
    lyrics = "[Verse]\nNou ka rive ansanm.\nNou gen espwa!"
    params = {"language": "ht", "music_style": "Konpa, duet, piano"}
    calls = []

    def request(method, path, payload=None, **kwargs):
        calls.append((method, path, payload))
        if method == "POST":
            return {"request_id": "offline-fal-request"}
        if path.endswith("/status"):
            return {"status": "COMPLETED"}
        return {"audio": {"url": "https://v3.fal.media/files/test/output.wav"}}

    monkeypatch.setattr(fal_client, "request", request)
    monkeypatch.setattr(
        providers, "discover", lambda: pytest.fail("Fal must not discover Google models")
    )
    # A real valid WAV validates the entire worker/storage/publication/debit path offline.
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000)
    audio = buffer.getvalue()

    def media(url, destination=None):
        assert url.startswith("https://v3.fal.media/")
        if destination:
            destination.write_bytes(audio)
            return destination
        return audio

    monkeypatch.setattr(fal_client, "media", media)
    quoted = client.post(
        "/v1/quotes",
        headers=auth,
        json={"studio": "music", "model_id": item["id"], "prompt": lyrics, "params": params},
    )
    assert quoted.status_code == 200, quoted.text
    amount = quoted.json()["credits"]
    assert amount > 0
    response = client.post(
        "/v1/jobs",
        headers=auth,
        json={
            "studio": "music",
            "model_id": item["id"],
            "prompt": lyrics,
            "params": params,
            "confirmed_credits": amount,
            "idempotency_key": "fal-real-worker-fixture",
        },
    )
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    assert "fal_profile" not in response.json()["params"]
    assert worker.run_once()
    done = client.get("/v1/jobs/" + identifier, headers=auth).json()
    assert done["status"] == "completed", done
    assert calls[0][2]["lyrics"] == lyrics and calls[0][2]["tags"] == params["music_style"]
    assert sum(method == "POST" for method, _, _ in calls) == 1
    assert not worker.run_once()
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == 100 - amount and wallet["reserved"] == 0
    with Session() as db:
        asset = db.get(Asset, done["params"]["result_asset_id"])
        assert asset and storage.get(asset.key) == audio
    replay = client.post(
        "/v1/jobs",
        headers=auth,
        json={
            "studio": "music",
            "model_id": item["id"],
            "prompt": lyrics,
            "params": params,
            "confirmed_credits": amount,
            "idempotency_key": "fal-real-worker-fixture",
        },
    )
    assert replay.status_code == 202 and replay.json()["id"] == identifier


@pytest.mark.parametrize(
    "adapter",
    [
        "ace_music",
        "minimax_music",
        "image",
        "background",
        "upscale",
        "image_edit",
        "voice",
        "text",
        "kling_video",
        "wan_video",
        "kling_audio",
        "kling_image_audio",
    ],
)
def test_all_studio_adapters_build_native_bounded_inputs(adapter):
    item = profile(adapter)
    params = {"language": "en", "music_style": "Piano, duet", "aspect": "16:9"}
    if item.get("reference_required"):
        params.update(
            reference_asset_id="private-asset", _fal_reference_url="https://private.example/image"
        )
    body = fal_inputs.payload(item, "Original content", params)
    assert set(body) <= set(item["input_schema"]["properties"])
    assert set(item["input_schema"].get("required", [])) <= set(body)
    if adapter in ("ace_music", "minimax_music"):
        assert body["lyrics"] == "Original content"
    if adapter == "minimax_music":
        assert body["lyrics_optimizer"] is False and "duration" not in body
    if adapter == "image":
        assert body["num_images"] == 1
    if adapter == "voice":
        assert body["voice"] == "af_heart"
    if adapter == "kling_image_audio":
        assert body["start_image_url"].startswith("https://private.example/")


def test_parameters_cannot_disable_safety_change_cost_fields_or_select_premium_model():
    for adapter, override in [
        ("image", {"num_images": 50}),
        ("ace_music", {"enable_safety_checker": False}),
        ("text", {"model": "openai/o3"}),
    ]:
        item = profile(adapter)
        with pytest.raises(ProviderError, match="FAL_INPUT_INVALID"):
            fal_inputs.payload(item, "Content", {"fal_inputs": override})


def test_real_native_limits_and_no_automatic_lyric_translation():
    item = profile()
    long = "\n".join(["We keep these exact supplied words"] * 200)
    assert fal_inputs.payload(item, long, {"music_style": "slow"})["duration"] == 240
    assert fal_inputs.quote(item, long, {"music_style": "slow"})["music_duration_limited"] is True
    with pytest.raises(ProviderError, match="FAL_PROMPT_TOO_LONG"):
        fal_inputs.payload(profile("minimax_music"), "x" * 3501, {})
    for adapter in ("voice", "kling_audio"):
        with pytest.raises(ProviderError, match="FAL_MODEL_LANGUAGE_UNSUPPORTED"):
            fal_inputs.payload(profile(adapter), "Pawòl mwen", {"language": "ht"})
    with pytest.raises(ProviderError, match="FAL_PRICING_UNIT_UNSUPPORTED"):
        fal_inputs.quote(
            {**profile("background"), "price_unit": "compute seconds"},
            "Remove background",
            {"reference_asset_id": "reference"},
        )


def test_queue_resume_uses_existing_request_without_post(monkeypatch):
    calls = []

    def request(method, path, *args, **kwargs):
        calls.append((method, path))
        assert method == "GET"
        return {"status": "COMPLETED"} if path.endswith("/status") else {"output": "Recovered"}

    monkeypatch.setattr(fal_client, "request", request)
    result = fal_client.run("fal-ai/any-llm", {}, {"_resume_operation_id": "existing-request"})
    assert result == {"output": "Recovered"} and len(calls) == 2
    assert calls[0][1] == "/fal-ai/any-llm/requests/existing-request/status"


def test_submission_marked_before_call_and_operation_saved_before_poll(monkeypatch):
    events = []

    def request(method, path, *args, **kwargs):
        events.append(method)
        if method == "POST":
            return {"request_id": "id-1", "status_url": "https://evil.invalid/steal"}
        return {"status": "COMPLETED"} if path.endswith("/status") else {"output": "done"}

    monkeypatch.setattr(fal_client, "request", request)
    fal_client.run(
        "fal-ai/kling-video/v3/standard/text-to-video",
        {},
        {
            "_submission_callback": lambda: events.append("checkpoint"),
            "_operation_callback": lambda i: events.append(i),
        },
    )
    assert events == ["checkpoint", "POST", "id-1", "GET", "GET"]


@pytest.mark.parametrize(
    "url",
    [
        "http://v3.fal.media/a",
        "https://fal.media.evil.invalid/a",
        "https://localhost/a",
        "https://169.254.169.254/a",
        "https://storage.googleapis.com/private-bucket/a",
        "https://v3.fal.media:8080/a",
        "https://key@v3.fal.media/a",
    ],
)
def test_media_rejects_untrusted_urls_without_transport(url, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "not-for-media-hosts")
    with pytest.raises(ProviderError, match="PROVIDER_MEDIA_DESTINATION_REJECTED"):
        fal_client.media(url)


def test_fal_credentials_only_api_hosts_and_no_automatic_queue_retry(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "offline-secret")
    observed = []
    original = httpx.Client

    def transport(request):
        observed.append(request)
        if request.url.host == "queue.fal.run":
            return httpx.Response(503, json={"detail": "temporary error"})
        return httpx.Response(200, content=b"private-file")

    monkeypatch.setattr(
        fal_client.httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(transport), **kw),
    )
    with pytest.raises(ProviderError, match="PROVIDER_HTTP_503"):
        fal_client.run("fal-ai/ace-step", {}, {})
    assert len(observed) == 1 and observed[0].headers["Authorization"] == "Key offline-secret"
    assert observed[0].headers["X-Fal-No-Retry"] == "1"
    assert fal_client.media("https://v3.fal.media/files/output") == b"private-file"
    assert "Authorization" not in observed[-1].headers


@pytest.mark.parametrize("drama_stage", [False, True])
def test_uncertain_submission_cannot_be_resubmitted_even_if_local_error_changes(
    client, monkeypatch, drama_stage
):
    configure(monkeypatch, "music", 32)
    user, auth = register(client)
    fund(user["id"], 100)
    item = profile()
    approve(user["id"], item, monkeypatch)
    params = {"language": "ht", "music_style": "Konpa"}
    q = client.post(
        "/v1/quotes",
        headers=auth,
        json={
            "studio": "music",
            "model_id": item["id"],
            "prompt": "Original lyrics",
            "params": params,
        },
    ).json()
    created = client.post(
        "/v1/jobs",
        headers=auth,
        json={
            "studio": "music",
            "model_id": item["id"],
            "prompt": "Original lyrics",
            "params": params,
            "confirmed_credits": q["credits"],
            "idempotency_key": "unknown-fal-submission",
        },
    ).json()
    with Session.begin() as db:
        row = db.get(Job, created["id"])
        row.status = "failed"
        row.error = "WORKER_PREPARATION_FAILED"
        row.params = {**row.params, "fal_submission_started": True, "failure_phase": "preparing"}
        if drama_stage:
            row.studio = "minidrama"
            row.error = "MEDIA_OR_STORAGE_FAILED"
            row.params = {
                **row.params, "input_params": {"mode": "episode"},
                "failure_phase": "provider",
                "remote_operation": {"id": "previous-paid-scene"},
                "provider_response": {"video": {"url": "https://fal.media/previous"}},
            }
    before = client.get("/v1/wallet", headers=auth).json()
    if drama_stage:
        assert client.get("/v1/jobs/" + created["id"], headers=auth).json()["retry_mode"] == "blocked"
    retry = client.post("/v1/jobs/" + created["id"] + "/retry", headers=auth)
    assert retry.status_code == 409 and retry.json()["detail"] == "MANUAL_RECONCILIATION_REQUIRED"
    assert client.get("/v1/wallet", headers=auth).json() == before


def test_admin_required_and_price_verification_does_not_generate(client, monkeypatch):
    _, auth = register(client)
    assert client.get("/v1/admin/fal", headers=auth).status_code == 403
    with Session.begin() as db:
        db.query(User).update({"role": "admin"})
    monkeypatch.setenv("FAL_KEY", "offline-admin-key")
    item = profile()
    calls = []

    def request(method, path, payload=None, **kwargs):
        calls.append((method, path))
        assert method == "GET"
        if path == "/models":
            return {
                "models": [
                    {
                        "endpoint_id": item["endpoint_id"],
                        "metadata": {"status": "active"},
                        "openapi": {
                            "components": {"schemas": {"AceStepInput": item["input_schema"]}}
                        },
                    }
                ]
            }
        return {
            "prices": [
                {
                    "endpoint_id": item["endpoint_id"],
                    "unit_price": 0.0002,
                    "unit": "seconds",
                    "currency": "USD",
                }
            ]
        }

    monkeypatch.setattr(fal_client, "request", request)
    response = client.post("/v1/admin/fal/models/" + item["id"] + "/verify", headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["price_verified"] and not response.json()["enabled"]
    response = client.put(
        "/v1/admin/fal/models/" + item["id"],
        headers=auth,
        json={
            "enabled": True,
            "operator_billing_ack": True,
            "license_ack": True,
            "expected_unit_price": "0.0002",
            "expected_unit": "seconds",
            "markup": "4",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] and all(method == "GET" for method, _ in calls)
    assert "offline-admin-key" not in client.get("/v1/admin/fal", headers=auth).text


def test_durable_config_uses_same_snapshot_for_merge_and_compare_and_swap(monkeypatch):
    from haytile import accounts

    item = profile()
    reads = []
    committed = []
    monkeypatch.setattr(accounts, "enabled", lambda: True)
    monkeypatch.setattr(
        accounts, "read", lambda *args: reads.append(args) or ({"payload": "[]"}, "version-1")
    )
    monkeypatch.setattr(
        accounts,
        "update_write",
        lambda *args, **kwargs: {"version": kwargs.get("version"), "payload": args[2]["payload"]},
    )
    monkeypatch.setattr(accounts, "audit_write", lambda *args: {"audit": True})
    monkeypatch.setattr(accounts, "commit", lambda writes: committed.extend(writes))
    fal_catalog.save(item, "offline-config-actor")
    assert len(reads) == 1
    assert committed[0]["version"] == "version-1"
    assert (
        next(row for row in json.loads(committed[0]["payload"]) if row["id"] == item["id"])[
            "enabled"
        ]
        is True
    )
    fal_catalog.invalidate()


def test_expanded_catalog_respects_official_ten_model_limit(monkeypatch):
    observed = []
    monkeypatch.setattr(fal_client, "request", lambda *args, **kwargs: observed.append(kwargs) or {})
    fal_client.catalog(identifier="fal-ai/ace-step", expand=True)
    fal_client.catalog(query="music")
    assert observed[0]["params"]["limit"] == 10
    assert observed[0]["params"]["expand"] == "openapi-3.0"
    assert observed[1]["params"]["limit"] == 25
