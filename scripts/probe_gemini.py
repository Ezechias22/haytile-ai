"""Read account-visible model metadata without generating content or logging secrets."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def collect_models(fetch):
    models, seen = [], set()
    token = None
    while True:
        query = {"pageSize": "1000"}
        if token:
            query["pageToken"] = token
        payload = fetch(BASE + "?" + urllib.parse.urlencode(query))
        batch = payload.get("models", [])
        if not isinstance(batch, list):
            raise ValueError("invalid model list")
        for model in batch:
            if not isinstance(model, dict) or not isinstance(model.get("name"), str):
                raise ValueError("invalid model metadata")
            models.append(
                {
                    k: model[k]
                    for k in (
                        "name",
                        "displayName",
                        "version",
                        "supportedGenerationMethods",
                        "inputTokenLimit",
                        "outputTokenLimit",
                    )
                    if k in model
                }
            )
        token = payload.get("nextPageToken")
        if not token:
            return models
        if not isinstance(token, str) or token in seen:
            raise ValueError("invalid pagination")
        seen.add(token)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the API key to a redirect destination.


def main():
    key = os.environ.get("HAYTILE_GEMINI_API_KEY")
    if not key:
        print("Missing HAYTILE_GEMINI_API_KEY; configure it securely on the backend.")
        return 2
    opener = urllib.request.build_opener(NoRedirect())

    def fetch(url):
        req = urllib.request.Request(url, headers={"x-goog-api-key": key})
        with opener.open(req, timeout=30) as response:
            return json.load(response)

    try:
        models = collect_models(fetch)
        if not models:
            print("No visible models; account access remains unverified.")
            return 1
        target = Path("artifacts/model-catalog.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"models": models}, indent=2) + "\n")
        print(f"{len(models)} visible model records saved to {target}.")
        print(
            "Generation access, pricing, quotas, region and licensing remain separate checks."
        )
        return 0
    except urllib.error.HTTPError as exc:
        print(f"Model discovery failed: HTTP {exc.code}. Response body omitted.")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        print(
            "Model discovery failed: network, response or local output error. Details omitted to protect credentials."
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
