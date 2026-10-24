"""Read Render workspaces without logging credentials or performing mutations."""

import json
import os
import sys

import httpx


def main():
    key = os.environ.get("HAYTILE_RENDER_API_KEY")
    if not key:
        print(
            "HAYTILE_RENDER_API_KEY is missing. Add it through secure environment settings."
        )
        return 2
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.get(
                "https://api.render.com/v1/owners",
                params={"limit": 20},
                headers={
                    "Authorization": "Bearer " + key,
                    "Accept": "application/json",
                },
            )
        if response.status_code != 200:
            print(
                f"Render access check failed: HTTP {response.status_code}. Response details omitted."
            )
            return 1
        entries = response.json()
        owners = []
        for entry in entries:
            owner = entry.get("owner", entry)
            owners.append({k: owner[k] for k in ("id", "name", "type") if k in owner})
        print(json.dumps({"owners": owners}, indent=2))
        return 0
    except (httpx.HTTPError, ValueError, TypeError):
        print("Render access check failed: network or response error. Details omitted.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
