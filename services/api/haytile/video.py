"""Assemble native generated clips without stretching or looping motion."""

import json
import subprocess
import tempfile
from pathlib import Path

from .providers import ProviderError


def probe(path):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=30,
    )
    if r.returncode:
        raise ProviderError("VIDEO_DECODE_FAILED")
    return json.loads(r.stdout)


def assemble(clips, duration, aspect="16:9", audio_required=True, clip_durations=None):
    if not 8 <= duration <= 180:
        raise ProviderError("VIDEO_DURATION_INVALID")
    if aspect not in ("16:9", "9:16"):
        raise ProviderError("VIDEO_ASPECT_INVALID")
    if clip_durations is not None and len(clip_durations) != len(clips):
        raise ProviderError("SCENE_DURATION_COUNT_INVALID")
    width, height = (1280, 720) if aspect == "16:9" else (720, 1280)
    with tempfile.TemporaryDirectory(prefix="haytile-video-") as tmp:
        root = Path(tmp)
        normalized = []
        total = 0.0
        for i, data in enumerate(clips):
            source = root / f"source-{i}.mp4"
            source.write_bytes(data)
            info = probe(source)
            seconds = float(info.get("format", {}).get("duration", 0))
            if clip_durations is not None:
                if seconds + 0.05 < clip_durations[i]:
                    raise ProviderError("VIDEO_TOO_SHORT_NO_STRETCH")
                seconds = clip_durations[i]
            has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
            if audio_required and not has_audio:
                raise ProviderError("VIDEO_AUDIO_MISSING")
            if (
                not any(s["codec_type"] == "video" for s in info["streams"])
                or seconds <= 0
            ):
                raise ProviderError("VIDEO_STREAM_INVALID")
            target = root / f"clip-{i}.mp4"
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(source)]
            if not has_audio:
                cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            cmd += [
                "-map",
                "0:v:0",
                "-map",
                "0:a:0" if has_audio else "1:a:0",
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-t",
                str(seconds),
                str(target),
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
            if proc.returncode:
                raise ProviderError("VIDEO_NORMALIZATION_FAILED")
            normalized.append(target)
            total += seconds
        if total + 0.05 < duration:
            raise ProviderError("VIDEO_TOO_SHORT_NO_STRETCH")
        manifest = root / "clips.txt"
        manifest.write_text("".join(f"file '{p.name}'\n" for p in normalized))
        output = root / "final.mp4"
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "1",
                "-i",
                str(manifest),
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "22",
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output),
            ],
            capture_output=True,
            timeout=180,
        )
        if result.returncode:
            raise ProviderError("VIDEO_ASSEMBLY_FAILED")
        final = probe(output)
        if abs(float(final["format"]["duration"]) - duration) > 0.15:
            raise ProviderError("VIDEO_FINAL_DURATION_FAILED")
        videos = [s for s in final["streams"] if s["codec_type"] == "video"]
        if not videos or (videos[0]["width"], videos[0]["height"]) != (width, height):
            raise ProviderError("VIDEO_FINAL_RESOLUTION_FAILED")
        return output.read_bytes()
