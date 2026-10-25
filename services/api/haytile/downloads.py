"""Single HTTP byte ranges for private media playback and bounded downloads."""

import re


def byte_range(header, size):
    if not header:
        return 0, size - 1
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or size <= 0:
        raise ValueError("RANGE_INVALID")
    first, last = match.groups()
    if not first and not last:
        raise ValueError("RANGE_INVALID")
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError("RANGE_INVALID")
        return max(0, size - length), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError("RANGE_INVALID")
    return start, end


def chunks(reader, length):
    try:
        while length > 0:
            data = reader.read(min(length, 64 * 1024))
            if not data:
                raise OSError("MEDIA_TRUNCATED")
            length -= len(data)
            yield data
    finally:
        reader.close()
