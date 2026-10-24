from .conftest import register
from .test_video import clip
from haytile.worker import run_once


def document():
    return {
        "premise": "Yon ti istwa",
        "continuity": "Same blue shirt",
        "aspect": "16:9",
        "characters": [
            {
                "id": "character-001",
                "name": "Mika",
                "appearance": "Short hair",
                "wardrobe": "Blue shirt",
                "voice": "Warm",
                "language": "ht",
            }
        ],
        "scenes": [
            {
                "id": "scene-001",
                "title": "Scene one",
                "description": "A garden",
                "dialogue": "Bonjou!",
                "duration": 8,
                "character_ids": ["character-001"],
            }
        ],
    }


def test_project_ownership_revision_and_exact_dialogue(client):
    _, a = register(client)
    first = client.post(
        "/v1/projects", json={"title": "Episode 1", "document": document()}, headers=a
    )
    assert first.status_code == 201, first.text
    p = first.json()
    assert p["document"]["scenes"][0]["dialogue"] == "Bonjou!"
    _, b = register(client, "other@example.test")
    assert client.get("/v1/projects", headers=b).json() == []
    assert client.put("/v1/projects/" + p["id"], json=p, headers=b).status_code == 404
    p["document"]["scenes"][0]["dialogue"] = "Pa chanje pawòl mwen."
    result = client.put("/v1/projects/" + p["id"], json=p, headers=a)
    assert result.status_code == 200
    assert result.json()["version"] == 2
    assert client.put("/v1/projects/" + p["id"], json=p, headers=a).status_code == 409
    assert (
        client.get("/v1/me/export", headers=a).json()["projects"][0]["document"][
            "scenes"
        ][0]["dialogue"]
        == "Pa chanje pawòl mwen."
    )


def test_project_rejects_invalid_character_reference_and_long_episode(client):
    _, h = register(client)
    doc = document()
    doc["scenes"][0]["character_ids"] = ["missing-id"]
    assert (
        client.post(
            "/v1/projects", json={"title": "Invalid", "document": doc}, headers=h
        ).status_code
        == 400
    )
    doc = document()
    doc["scenes"] = [
        dict(doc["scenes"][0], id=f"scene-{i:04d}", duration=10) for i in range(19)
    ]
    assert (
        client.post(
            "/v1/projects", json={"title": "Too long", "document": doc}, headers=h
        ).status_code
        == 400
    )


def test_uploaded_scene_to_final_episode_real_worker(client, tmp_path):
    _, h = register(client)
    data = clip(tmp_path / "scene.mp4", "green", 8)
    upload = client.post(
        "/v1/assets/upload", files={"file": ("scene.mp4", data, "video/mp4")}, headers=h
    )
    assert upload.status_code == 201, upload.text
    doc = document()
    doc["scenes"][0]["asset_id"] = upload.json()["id"]
    p = client.post(
        "/v1/projects", json={"title": "Finished episode", "document": doc}, headers=h
    ).json()
    request = {"idempotency_key": "assembly-once-0001"}
    a = client.post("/v1/projects/" + p["id"] + "/assemble", json=request, headers=h)
    assert a.status_code == 202, a.text
    b = client.post("/v1/projects/" + p["id"] + "/assemble", json=request, headers=h)
    assert a.json()["id"] == b.json()["id"]
    assert run_once()
    jobs = client.get("/v1/jobs", headers=h).json()
    assert jobs[0]["status"] == "completed", jobs
    assets = client.get("/v1/assets", headers=h).json()
    final = next(a for a in assets if a["title"] == "Finished episode")
    link = client.get("/v1/assets/" + final["id"] + "/link", headers=h).json()["path"]
    download = client.get(link)
    assert (
        download.status_code == 200 and download.headers["content-type"] == "video/mp4"
    )
    wallet = client.get("/v1/wallet", headers=h).json()
    assert (
        wallet["balance"] == 0
        and wallet["reserved"] == 0
        and wallet["transactions"] == []
    )
