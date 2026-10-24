"""Stop only the API/worker/web process trees recorded by scripts/start.sh."""

import os
from pathlib import Path
import signal
import subprocess

root = Path("/workspace/haytile-ai/.local")
expected = {
    "api": "uvicorn haytile.main:app",
    "worker": "-m haytile.worker",
    "web": "npm run start",
}
rows = subprocess.check_output(["ps", "-e", "-o", "pid=,ppid="], text=True).splitlines()
parents = {
    int(parts[0]): int(parts[1]) for line in rows if len(parts := line.split()) == 2
}
for name, signature in expected.items():
    path = root / (name + ".pid")
    if not path.exists():
        continue
    try:
        pid = int(path.read_text().strip())
        command = (
            Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
        )
        if signature not in command:
            print(f"{name}: stale PID ignored")
            continue
        descendants = {pid}
        while True:
            more = {p for p, parent in parents.items() if parent in descendants}
            if more <= descendants:
                break
            descendants |= more
        for child in sorted(descendants - {pid}, reverse=True):
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        print(f"{name}: stopped")
    except (OSError, ValueError):
        print(f"{name}: not running")
    finally:
        path.unlink(missing_ok=True)
