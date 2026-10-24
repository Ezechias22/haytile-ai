import json

import pytest

from haytile import bootstrap, providers
from haytile.db import Model, Session


def test_model_activation_requires_operator_approval(monkeypatch):
    monkeypatch.setenv(
        "HAYTILE_MODEL_CONFIG",
        json.dumps([{"studio": "text", "model_id": "fixture-model"}]),
    )
    monkeypatch.delenv("HAYTILE_OPERATOR_BILLING_ACK", raising=False)
    with pytest.raises(RuntimeError, match="approval"):
        bootstrap.configure_models()


def test_only_account_visible_models_are_activated(monkeypatch):
    monkeypatch.setenv(
        "HAYTILE_MODEL_CONFIG",
        json.dumps(
            [
                {"studio": "text", "model_id": "visible-fixture"},
                {"studio": "voice", "model_id": "unavailable-fixture"},
            ]
        ),
    )
    monkeypatch.setenv("HAYTILE_OPERATOR_BILLING_ACK", "1")
    monkeypatch.setattr(
        providers, "discover", lambda: [{"name": "models/visible-fixture"}]
    )
    bootstrap.configure_models()
    with Session() as db:
        assert db.get(Model, "text").enabled
        assert not db.get(Model, "voice").enabled
