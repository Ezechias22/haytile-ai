import io
import json
import subprocess
import tempfile

from PIL import Image

MAX_BYTES = 30 * 1024 * 1024


def inspect_media(data, requested_mime, max_bytes=MAX_BYTES):
    if not data or len(data) > max_bytes:
        raise ValueError("FILE_SIZE")
    if requested_mime == "text/plain":
        text = data.decode("utf-8")
        if "\x00" in text:
            raise ValueError("FILE_TYPE")
        return "text/plain", text
    if requested_mime.startswith("image/"):
        Image.MAX_IMAGE_PIXELS = 20_000_000
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > 20_000_000:
                raise ValueError("IMAGE_TOO_LARGE")
            img.verify()
            mime = Image.MIME.get(img.format)
        if mime not in ("image/png", "image/jpeg", "image/webp"):
            raise ValueError("FILE_TYPE")
        return mime, None
    if not requested_mime.startswith(("audio/", "video/")):
        raise ValueError("FILE_TYPE")
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(data)
        tmp.flush()
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                tmp.name,
            ],
            capture_output=True,
            timeout=20,
        )
        if proc.returncode:
            raise ValueError("MEDIA_INVALID")
        decode = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-threads",
                "2",
                "-i",
                tmp.name,
                "-map",
                "0:v?",
                "-map",
                "0:a?",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=90,
        )
        if decode.returncode:
            raise ValueError("MEDIA_CORRUPT")
        info = json.loads(proc.stdout)
        duration = float(info.get("format", {}).get("duration", 0))
        if not 0 < duration <= 600:
            raise ValueError("MEDIA_DURATION")
        types = {s.get("codec_type") for s in info.get("streams", [])}
        fmt = info.get("format", {}).get("format_name", "")
        if "video" in types:
            if "mp4" not in fmt:
                raise ValueError("VIDEO_FORMAT_USE_MP4")
            return "video/mp4", None
        if "audio" not in types:
            raise ValueError("MEDIA_INVALID")
        if fmt == "wav":
            return "audio/wav", None
        if fmt == "mp3":
            return "audio/mpeg", None
        if "ogg" in fmt:
            return "audio/ogg", None
        raise ValueError("AUDIO_FORMAT_USE_WAV_MP3_OGG")
