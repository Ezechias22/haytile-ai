import subprocess
from pathlib import Path
import pytest
from haytile.video import assemble, probe
from haytile.providers import ProviderError
from .conftest import register
from .test_core import configure, job_request, fund


def clip(path, color, duration, audio=True):
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=160x90:r=24",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    command += [
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
    ]
    if audio:
        command += ["-c:a", "aac"]
    subprocess.run(command + [str(path)], check=True, capture_output=True)
    return path.read_bytes()


def test_ffmpeg_assembly_real_files_duration_resolution_audio_and_order(tmp_path):
    red = clip(tmp_path / "red.mp4", "red", 4)
    blue = clip(tmp_path / "blue.mp4", "blue", 5)
    result = assemble([red, blue], 8, "16:9")
    output = tmp_path / "final.mp4"
    output.write_bytes(result)
    info = probe(output)
    assert abs(float(info["format"]["duration"]) - 8) < 0.15
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (stream["width"], stream["height"]) == (1280, 720)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    for second, channel in [(1, 0), (6, 2)]:
        frame = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(second),
                "-i",
                str(output),
                "-frames:v",
                "1",
                "-vf",
                "scale=1:1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-threads",
                "1",
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout
        assert (
            frame[channel]
            > max(frame[(channel + 1) % 3], frame[(channel + 2) % 3]) + 80
        )


def test_assembly_refuses_stretch_and_missing_audio(tmp_path):
    short = clip(tmp_path / "short.mp4", "red", 1)
    with pytest.raises(ProviderError, match="TOO_SHORT"):
        assemble([short], 8)
    silent = clip(tmp_path / "silent.mp4", "blue", 1, False)
    with pytest.raises(ProviderError, match="AUDIO_MISSING"):
        assemble([silent], 8)


def test_video_duration_and_quote_validated(client, monkeypatch):
    configure(monkeypatch, "video", 5)
    u, h = register(client)
    fund(u["id"], 100)
    body = job_request("video", 5)
    body["params"] = {"duration": 181, "aspect": "16:9"}
    assert client.post("/v1/jobs", json=body, headers=h).status_code == 400
    body["params"]["duration"] = 25
    assert client.post("/v1/jobs", json=body, headers=h).status_code == 409
    body["confirmed_credits"] = 15
    assert client.post("/v1/jobs", json=body, headers=h).status_code == 202
