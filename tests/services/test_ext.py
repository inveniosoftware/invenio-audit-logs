# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Test extension config validation."""

import pytest


def test_validate_actions_config_rejects_unknown(app, monkeypatch):
    """Unknown action names in the config fail validation."""
    ext = app.extensions["invenio-audit-logs"]
    monkeypatch.setitem(
        app.config, "AUDIT_LOGS_ENABLED_ACTIONS", {"draft.create", "does.not.exist"}
    )
    with pytest.raises(RuntimeError, match="Unknown audit log actions"):
        ext.validate_actions_config(app)


def test_validate_actions_config_rejects_overlap(app, monkeypatch):
    """An action in both the allow- and deny-list fails validation."""
    ext = app.extensions["invenio-audit-logs"]
    monkeypatch.setitem(app.config, "AUDIT_LOGS_ENABLED_ACTIONS", {"draft.create"})
    monkeypatch.setitem(app.config, "AUDIT_LOGS_DISABLED_ACTIONS", {"draft.create"})
    with pytest.raises(RuntimeError, match="both"):
        ext.validate_actions_config(app)
