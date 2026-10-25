"""Apply operator-approved server-side model configuration, never guessed IDs."""

import json
import logging
import os

from . import providers
from .availability import generation_enabled
from .db import Audit, Model, Session, now

log = logging.getLogger("haytile.bootstrap")


def configure_models():
    if not generation_enabled():
        return
    raw = os.environ.get("HAYTILE_MODEL_CONFIG")
    if not raw:
        return
    if os.environ.get("HAYTILE_OPERATOR_BILLING_ACK") != "1":
        raise RuntimeError(
            "Operator model billing approval is required before activation."
        )
    entries = json.loads(raw)
    if not isinstance(entries, list) or len(entries) > 6:
        raise RuntimeError("Invalid model configuration.")
    allowed = {"image", "text", "voice", "music", "video", "minidrama"}
    for item in entries:
        if (
            not isinstance(item, dict)
            or item.get("studio") not in allowed
            or not isinstance(item.get("model_id"), str)
        ):
            raise RuntimeError("Invalid model configuration.")
        credits = item.get("credits", 0)
        if type(credits) is not int or not 0 <= credits <= 100000:
            raise RuntimeError("Invalid model credit configuration.")
        if credits != 0 and item["studio"] == "image":
            raise RuntimeError("Basic images must remain zero-credit.")
    try:
        names = {m["name"] for m in providers.discover()}
    except providers.ProviderError:
        log.warning(
            "Provider catalog check failed; model configuration was not activated."
        )
        return
    with Session.begin() as db:
        for item in entries:
            studio = item["studio"]
            model_id = item["model_id"]
            available = "models/" + model_id in names
            row = db.get(Model, studio)
            if not row:
                row = Model(
                    studio=studio,
                    model_id=model_id,
                    price_source="https://ai.google.dev/gemini-api/docs/pricing",
                )
                db.add(row)
            row.model_id = model_id
            row.credits = int(item.get("credits", 0))
            row.enabled = available
            row.verified_at = now()
            db.add(
                Audit(
                    actor_id="operator-runtime",
                    action="model.runtime_configure",
                    details={
                        "studio": studio,
                        "model_id": model_id,
                        "catalog_visible": available,
                    },
                )
            )
            if not available:
                log.warning(
                    "Configured model is absent from the account catalog: studio=%s",
                    studio,
                )
