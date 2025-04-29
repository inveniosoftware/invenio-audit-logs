# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Action system field for record."""

import inspect
from invenio_records.systemfields import ModelField
from ...proxies import current_audit_logs_actions_registry

from ...actions import AuditAction


class ActionField(ModelField):
    """Systemfield for managing the audit action (e.g., 'draft.create')."""

    @staticmethod
    def get_instance(action):
        """Ensure that always an instance of AuditAction is returned."""
        if isinstance(action, str):
            action = current_audit_logs_actions_registry[action]

        if not isinstance(action, AuditAction):
            raise TypeError(f"Expected 'AuditAction' but got: '{type(action)}'")
        return action

    def _set(self, model, action):
        """Set the model value (stores action ID as string)."""
        action = self.get_instance(action)
        super()._set(model, action.name)

    def set_obj(self, instance, obj):
        """Set the field from an AuditAction object."""
        self.set_dictkey(instance, obj.name)
        self._set_cache(instance, obj)
        self._set(instance.model, obj)

    def __set__(self, record, action_name):
        """Set field on record."""
        assert record is not None
        action = self.get_instance(action_name)
        self.set_obj(record, action)

    def obj(self, instance):
        """Get the AuditAction instance."""
        obj = self._get_cache(instance)
        if obj is not None:
            return obj

        action_name = super().__get__(instance)
        if not action_name:
            action_name = self.get_dictkey(instance)

        obj = self.get_instance(action_name)
        self._set_cache(instance, obj)

        return obj

    def __get__(self, record, owner=None):
        """Get the AuditAction instance (record-level access)."""
        if record is None:
            return self
        return self.obj(record)

    #
    # Record extension
    #
    def pre_init(self, record, data, model=None, **kwargs):
        """Ensure action is valid and resolved through registry."""
        _action = kwargs.get("action")
        if _action is None:
            _action = model.action  # fallback from model

        action_obj = self.get_instance(_action)
        try:
            current_audit_logs_actions_registry[action_obj.name]
        except KeyError:
            raise TypeError(f"Audit action '{action_obj.name}' is not registered.")
