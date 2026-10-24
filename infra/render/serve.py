"""Supervise the web, API and queue worker in one persistent Render instance.

This initial deployment intentionally uses a single instance: private disk files
cannot be shared between Render instances. PostgreSQL remains the durable queue.
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(os.environ.get("HAYTILE_APP_ROOT", "/app"))
DATA = Path(os.environ.get("HAYTILE_DATA_DIR", "/var/data/haytile"))


def prepare_environment():
    env = os.environ.copy()
    env.setdefault("HAYTILE_DATA_DIR", str(DATA))
    env.setdefault("HAYTILE_API_URL", "http://127.0.0.1:8000")
    env.setdefault("PYTHONPATH", str(APP / "services/api"))
    if not env.get("HAYTILE_PUBLIC_ORIGIN"):
        external = env.get("RENDER_EXTERNAL_URL", "")
        if not external.startswith("https://"):
            raise RuntimeError("A public HTTPS origin is required on Render.")
        env["HAYTILE_PUBLIC_ORIGIN"] = external.rstrip("/")
    if not env.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required.")
    return env


def drop_privileges():
    DATA.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        # Only this app-owned subdirectory is changed; do not chown arbitrary disk contents.
        os.chown(DATA, 1000, 1000)
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
    DATA.chmod(0o700)


def ready(url, process, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("A required child service exited during startup.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            time.sleep(0.25)
    raise RuntimeError("Service readiness timed out.")


def main():
    processes = []
    shutting_down = False

    def stop(signum=None, frame=None):
        nonlocal shutting_down
        shutting_down = True
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        env = prepare_environment()
        drop_privileges()
        # Migrations run with the runtime disk present, before any traffic or worker.
        subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=APP / "services/api",
            env=env,
            check=True,
            timeout=120,
        )
        subprocess.run(
            [
                "python",
                "-c",
                "from haytile.bootstrap import configure_models; configure_models()",
            ],
            cwd=APP / "services/api",
            env=env,
            check=True,
            timeout=60,
        )
        api = subprocess.Popen(
            [
                "python",
                "-m",
                "uvicorn",
                "haytile.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=APP / "services/api",
            env=env,
        )
        processes.append(api)
        ready("http://127.0.0.1:8000/v1/health", api)
        worker = subprocess.Popen(
            ["python", "-m", "haytile.worker"], cwd=APP / "services/api", env=env
        )
        processes.append(worker)
        port = str(int(env.get("PORT", "10000")))
        web = subprocess.Popen(
            [
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "--hostname",
                "0.0.0.0",
                "--port",
                port,
            ],
            cwd=APP / "apps/web",
            env=env,
        )
        processes.append(web)
        ready(f"http://127.0.0.1:{port}/api/v1/health", web)
        print("Haytile web, API and worker are ready.", flush=True)
        while not shutting_down:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("A required child service stopped.")
            time.sleep(0.5)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError):
        # Do not print environment values or database connection strings.
        print(
            "Haytile startup or service supervision failed; inspect service logs.",
            file=sys.stderr,
        )
        return 1
    finally:
        stop()
        deadline = time.monotonic() + 10
        for process in reversed(processes):
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
