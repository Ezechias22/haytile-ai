"""Create only a free Haytile Render service after the tested source is pushed.

No paid resource, disk, database, model activation or unrelated service update.
The private control key is never forwarded into the app environment.
"""

import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local" / "render-free-state.json"
REPO = "https://github.com/Ezechias22/haytile-ai"


def safe_error(response, key):
    if "application/json" not in response.headers.get("content-type", ""):
        return "Non-JSON response body omitted."
    try:
        message = response.json().get("message", "")
        if not isinstance(message, str):
            return "Error details omitted."
        return re.sub(
            r"rnd_[A-Za-z0-9_-]+", "[redacted]", message.replace(key, "[redacted]")
        )[:300]
    except ValueError:
        return "Error details omitted."


def main():
    key = os.environ.get("HAYTILE_RENDER_API_KEY")
    if not key:
        raise SystemExit("Render control binding is missing.")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/main"], cwd=ROOT, text=True
    ).split()
    if not remote or remote[0] != head:
        raise SystemExit(
            "The tested commit must be pushed to origin/main before deployment."
        )
    STATE.parent.mkdir(exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
        response = client.get(
            "https://api.render.com/v1/services", headers=headers, params={"limit": 100}
        )
        if response.status_code != 200:
            raise SystemExit(
                "Render service inventory check failed: HTTP "
                + str(response.status_code)
            )
        records = response.json()
        if len(records) >= 100:
            raise SystemExit(
                "Inventory pagination must be completed before creating a service."
            )
        services = [x.get("service", x) for x in records]
        owners = {x["ownerId"] for x in services}
        if len(owners) != 1:
            raise SystemExit("A single Render workspace could not be inferred safely.")
        owner = next(iter(owners))
        existing = [x for x in services if x.get("name") == "haytile-ai"]
        if existing:
            service = existing[0]
            if (
                service.get("repo", "").removesuffix(".git") != REPO
                or service.get("serviceDetails", {}).get("plan") != "free"
            ):
                raise SystemExit(
                    "An existing service with this name cannot be safely reused automatically."
                )
            print(
                json.dumps(
                    {
                        "service_id": service["id"],
                        "url": service.get("serviceDetails", {}).get("url"),
                        "plan": "free",
                        "existing": True,
                    }
                )
            )
            return 0
        if state.get("service_create_attempted"):
            raise SystemExit(
                "A prior creation attempt is recorded; reconcile it before sending another mutation."
            )
        env = {
            "DATABASE_URL": "sqlite:////tmp/haytile/haytile.db",
            "HAYTILE_DATA_DIR": "/tmp/haytile",
            "HAYTILE_ENV": "production",
            "HAYTILE_FREE_BETA": "1",
            "HAYTILE_DAILY_JOB_LIMIT": "10",
            "HAYTILE_SIGNING_KEY": secrets.token_hex(32),
        }
        body = {
            "name": "haytile-ai",
            "type": "web_service",
            "ownerId": owner,
            "repo": REPO,
            "branch": "main",
            "autoDeployTrigger": "off",
            "envVars": [{"key": k, "value": v} for k, v in env.items()],
            "serviceDetails": {
                "runtime": "docker",
                "plan": "free",
                "region": "ohio",
                "numInstances": 1,
                "healthCheckPath": "/api/v1/health",
                "envSpecificDetails": {
                    "dockerfilePath": "./infra/render/Dockerfile",
                    "dockerContext": ".",
                },
            },
        }
        assert (
            body["serviceDetails"]["plan"] == "free"
            and "disk" not in body["serviceDetails"]
        )
        assert not any("API_KEY" in v["key"] for v in body["envVars"])
        state.update(
            {"owner_id": owner, "service_create_attempted": True, "source_commit": head}
        )
        STATE.write_text(json.dumps(state))
        STATE.chmod(0o600)
        response = client.post(
            "https://api.render.com/v1/services", headers=headers, json=body
        )
        state["service_http_status"] = response.status_code
        if not response.is_success:
            STATE.write_text(json.dumps(state))
            print(
                "Create free web service: HTTP",
                response.status_code,
                safe_error(response, key),
            )
            return 1
        result = response.json()
        service = result.get("service", result)
        state.update(
            {
                "service_id": service.get("id"),
                "deploy_id": result.get("deployId"),
                "url": service.get("serviceDetails", {}).get("url"),
                "plan": "free",
            }
        )
        STATE.write_text(json.dumps(state))
        print(
            json.dumps(
                {k: state.get(k) for k in ["service_id", "deploy_id", "url", "plan"]},
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPError:
        raise SystemExit(
            "Render request failed. Reconcile the recorded operation before any retry; no credentials were logged."
        )
