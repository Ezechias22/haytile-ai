"""Exercise a local Render-like container, its real worker and private storage.

No provider generation or paid API calls. Creates and removes its own test account.
Use only on a disposable local Docker deployment.
"""

import argparse
import json
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="/tmp/haytile-render-smoke.json")
    parser.add_argument("--base", default="http://localhost:3001")
    args = parser.parse_args()
    if args.base not in ("http://localhost:3001", "http://127.0.0.1:3001"):
        raise SystemExit(
            "This destructive smoke test only targets the disposable local deployment."
        )
    deployment = json.loads(Path(args.manifest).read_text())
    email = "render-smoke-" + secrets.token_hex(6) + "@example.test"
    password = secrets.token_urlsafe(24)
    api = args.base + "/api/v1"
    headers = {}
    with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:

        def request(method, path, **kwargs):
            response = client.request(method, api + path, headers=headers, **kwargs)
            if not response.is_success:
                raise RuntimeError(
                    f"{method} {path.split('?')[0]} failed: HTTP {response.status_code}"
                )
            return response

        try:
            result = request(
                "POST",
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "name": "Render smoke test",
                    "locale": "ht",
                },
            ).json()
            headers["Authorization"] = "Bearer " + result["token"]
            asset = request(
                "POST",
                "/assets/text",
                json={"title": "Persisted draft", "text": "Pa chanje pawòl mwen."},
            ).json()
            signed = request("GET", "/assets/" + asset["id"] + "/link").json()["path"]
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "scene.mp4"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=blue:s=160x90:r=24",
                        "-f",
                        "lavfi",
                        "-i",
                        "sine=frequency=440:sample_rate=48000",
                        "-t",
                        "8",
                        "-c:v",
                        "libx264",
                        "-threads",
                        "1",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        str(source),
                    ],
                    check=True,
                    capture_output=True,
                )
                clip = request(
                    "POST",
                    "/assets/upload",
                    files={"file": ("scene.mp4", source.read_bytes(), "video/mp4")},
                ).json()
                project = request(
                    "POST",
                    "/projects",
                    json={
                        "title": "Render worker episode",
                        "document": {
                            "premise": "Local assembly test",
                            "aspect": "16:9",
                            "characters": [],
                            "scenes": [
                                {
                                    "id": "render-scene-0001",
                                    "title": "Scene",
                                    "duration": 8,
                                    "description": "Blue frame",
                                    "dialogue": "",
                                    "character_ids": [],
                                    "asset_id": clip["id"],
                                }
                            ],
                        },
                    },
                ).json()
                job = request(
                    "POST",
                    "/projects/" + project["id"] + "/assemble",
                    json={"idempotency_key": "render-smoke-" + secrets.token_hex(10)},
                ).json()
                for _ in range(120):
                    state = next(
                        x
                        for x in request("GET", "/jobs").json()
                        if x["id"] == job["id"]
                    )
                    if state["status"] == "completed":
                        break
                    if state["status"] == "failed":
                        raise RuntimeError(
                            "Container worker assembly failed: " + str(state["error"])
                        )
                    time.sleep(1)
                else:
                    raise RuntimeError("Container worker did not finish the episode.")
                output = next(
                    x
                    for x in request("GET", "/assets").json()
                    if x["job_id"] == job["id"]
                )
                link = request("GET", "/assets/" + output["id"] + "/link").json()[
                    "path"
                ]
                final = Path(directory) / "final.mp4"
                response = client.get(args.base + "/api" + link)
                response.raise_for_status()
                final.write_bytes(response.content)
                media = json.loads(
                    subprocess.check_output(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_format",
                            "-show_streams",
                            "-of",
                            "json",
                            str(final),
                        ]
                    )
                )
                assert abs(float(media["format"]["duration"]) - 8) < 0.15
                assert any(s["codec_type"] == "audio" for s in media["streams"])
                video = next(s for s in media["streams"] if s["codec_type"] == "video")
                assert (video["width"], video["height"]) == (1280, 720)
            print(
                "Real container worker: upload -> queue -> FFmpeg -> private final download passed."
            )
            # Terminate only the known child worker and verify supervisor failure propagation.
            code = """import os,signal
for pid in os.listdir('/proc'):
 if not pid.isdigit(): continue
 try:
  command=open('/proc/'+pid+'/cmdline','rb').read().split(b'\\0')
  if b'haytile.worker' in command: os.kill(int(pid),signal.SIGTERM)
 except OSError: pass
"""
            subprocess.run(
                ["docker", "exec", deployment["app"], "python", "-c", code],
                check=True,
                capture_output=True,
            )
            for _ in range(30):
                status = subprocess.check_output(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.State.Status}}",
                        deployment["app"],
                    ],
                    text=True,
                ).strip()
                if status == "exited":
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Supervisor did not terminate after worker failure.")
            subprocess.run(
                ["docker", "restart", deployment["app"]],
                check=True,
                capture_output=True,
            )
            for _ in range(60):
                try:
                    if client.get(api + "/health", timeout=2).is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("Restart failed readiness.")
            assert any(x["id"] == asset["id"] for x in request("GET", "/assets").json())
            assert (
                client.get(args.base + "/api" + signed).text == "Pa chanje pawòl mwen."
            )
            assert request("GET", "/wallet").json()["balance"] == 0
            print(
                "Supervisor fail-closed, container restart, database/media/session/signature persistence and zero-credit assembly passed."
            )
        finally:
            if headers:
                try:
                    request("DELETE", "/me", json={"password": password})
                except (RuntimeError, httpx.HTTPError):
                    print(
                        "Test account cleanup needs checking in the disposable database."
                    )


if __name__ == "__main__":
    main()
