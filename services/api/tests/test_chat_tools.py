import base64
import io
import uuid

import pytest
from fastapi import HTTPException
from PIL import Image
from pypdf import PdfWriter

from haytile import providers, worker
from haytile.chat_tools import grounding, validate
from haytile.db import Job, Session

from .conftest import register
from .test_core import configure, job_request


def pdf(pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    if encrypted:
        writer.encrypt("private")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def chat(params=None, prompt="Read the attached document"):
    return {
        **job_request("text", 0, key=str(uuid.uuid4()), prompt=prompt),
        "params": {"chat": True, "conversation_id": str(uuid.uuid4()), **(params or {})},
    }


def test_images_pdf_search_and_followup_are_private_and_durable(client, monkeypatch):
    configure(monkeypatch, "text")
    user, auth = register(client)
    image = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(image, "PNG")
    picture = image.getvalue()
    document = pdf()
    ids = []
    for name, data, mime in [
        ("reference.png", picture, "image/png"),
        ("report.pdf", document, "application/pdf"),
    ]:
        response = client.post(
            "/v1/assets/upload", headers=auth, files={"file": (name, data, mime)}
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    link = client.get("/v1/assets/" + ids[1] + "/link", headers=auth).json()
    from urllib.parse import urlsplit

    path = urlsplit(link.get("media_url") or link["path"])
    download = client.get(path.path + "?" + path.query)
    assert download.status_code == 200
    assert download.content == document
    assert ".pdf" in download.headers["content-disposition"]
    calls = []

    def transport(method, path, payload=None, **kwargs):
        calls.append(payload)
        assert payload["tools"] == [{"googleSearch": {}}]
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "The attached report and image match the current source."}
                        ]
                    },
                    "groundingMetadata": {
                        "webSearchQueries": ["public information"],
                        "groundingChunks": [
                            {
                                "web": {
                                    "uri": "https://example.org/source",
                                    "title": "Verified source",
                                }
                            }
                        ],
                        "searchEntryPoint": {
                            "renderedContent": '<a href="https://google.com/search?q=public">Search</a>'
                        },
                    },
                }
            ]
        }

    monkeypatch.setattr(providers, "request", transport)
    body = chat({"attachment_ids": ids})
    result = client.post("/v1/jobs", headers=auth, json=body)
    assert result.status_code == 202, result.text
    assert worker.run_once()
    sent = calls[0]["contents"][-1]["parts"]
    assert base64.b64decode(sent[1]["inlineData"]["data"]) == picture
    assert base64.b64decode(sent[2]["inlineData"]["data"]) == document
    assert sent[2]["inlineData"]["mimeType"] == "application/pdf"
    history = client.get(
        "/v1/chat/conversations/" + body["params"]["conversation_id"], headers=auth
    ).json()
    assert (
        history[0]["params"]["chat_grounding"]["sources"][0]["url"] == "https://example.org/source"
    )
    with Session() as db:
        saved = db.get(Job, result.json()["id"]).params
        assert base64.b64encode(document).decode() not in str(saved)
    follow = chat(
        {
            "conversation_id": body["params"]["conversation_id"],
            "parent_job_id": result.json()["id"],
        },
        "Summarize the same PDF again",
    )
    assert client.post("/v1/jobs", headers=auth, json=follow).status_code == 202
    assert worker.run_once()
    assert calls[1]["contents"][0]["parts"][2]["inlineData"]["mimeType"] == "application/pdf"
    _, stranger = register(client, "outsider@example.test")
    forbidden = client.post("/v1/jobs", headers=stranger, json=chat({"attachment_ids": ids}))
    assert forbidden.status_code == 400
    assert client.get("/v1/assets/" + ids[1] + "/link", headers=stranger).status_code == 404
    assert len(calls) == 2


@pytest.mark.parametrize("data", [b"not a PDF", pdf(11), pdf(encrypted=True)])
def test_invalid_encrypted_and_large_page_pdfs_rejected(client, data):
    _, auth = register(client)
    result = client.post(
        "/v1/assets/upload", headers=auth, files={"file": ("invalid.pdf", data, "application/pdf")}
    )
    assert result.status_code == 400


def test_location_request_requires_consent_and_does_not_follow_user(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    calls = []

    def transport(method, path, payload=None, **kwargs):
        calls.append(payload)
        answer = (
            "Share your position to find nearby help. [HAYTILE_REQUEST_LOCATION]"
            if len(calls) == 1
            else "Here is nearby help."
        )
        return {"candidates": [{"content": {"parts": [{"text": answer}]}}]}

    monkeypatch.setattr(providers, "request", transport)
    first = chat(prompt="Find a nearby pharmacy")
    r = client.post("/v1/jobs", headers=auth, json=first)
    assert r.status_code == 202
    assert worker.run_once()
    history = client.get(
        "/v1/chat/conversations/" + first["params"]["conversation_id"], headers=auth
    ).json()
    assert history[0]["params"]["chat_location_requested"] is True
    assert "[HAYTILE_REQUEST_LOCATION]" not in history[0]["reply"]
    assert "latitude" not in str(calls[0]["contents"])
    second = chat(
        {
            "conversation_id": first["params"]["conversation_id"],
            "parent_job_id": r.json()["id"],
            "location": {"latitude": 18.54, "longitude": -72.34},
        },
        prompt=first["prompt"],
    )
    r = client.post("/v1/jobs", headers=auth, json=second)
    assert r.status_code == 202
    assert worker.run_once()
    assert "18.540" in str(calls[1]["contents"][-1])
    third = chat(
        {"conversation_id": first["params"]["conversation_id"], "parent_job_id": r.json()["id"]},
        prompt="Write a song",
    )
    assert client.post("/v1/jobs", headers=auth, json=third).status_code == 202
    assert worker.run_once()
    assert "18.540" not in str(calls[2]["contents"])
    with Session() as db:
        params = db.get(Job, r.json()["id"]).params
        assert "chat_grounding" not in params  # Ordinary replies have no noisy empty source panel.


@pytest.mark.parametrize(
    "location",
    [
        {"latitude": True, "longitude": 0},
        {"latitude": 91, "longitude": 0},
        {"latitude": 0, "longitude": 181},
        {"latitude": float("nan"), "longitude": 0},
        {"latitude": 0},
    ],
)
def test_invalid_locations_are_rejected_without_provider(location):
    with Session() as db, pytest.raises(HTTPException):
        validate(db, "unused", {"location": location})


def test_sources_reject_unsafe_urls_and_deduplicate():
    result = grounding(
        {
            "groundingChunks": [
                {"web": {"uri": "javascript:alert(1)"}},
                {"web": {"uri": "https://user:pass@example.org"}},
                {"web": {"uri": "https://example.org", "title": "A"}},
                {"web": {"uri": "https://example.org", "title": "B"}},
            ]
        }
    )
    assert result["sources"] == [{"url": "https://example.org", "title": "A"}]


def test_grounded_claim_citations_use_unicode_byte_offsets():
    from haytile.chat_tools import cite_parts

    parts = [{"text": "Enfòmasyon verifye. Another claim."}]
    metadata = {
        "groundingChunks": [{"web": {"uri": "https://example.org/source", "title": "Source"}}],
        "groundingSupports": [
            {
                "segment": {"partIndex": 0, "endIndex": len("Enfòmasyon verifye.".encode())},
                "groundingChunkIndices": [0],
            }
        ],
    }
    assert cite_parts(parts, metadata)[0]["text"] == "Enfòmasyon verifye. [1] Another claim."
    assert "[1]" not in parts[0]["text"]
