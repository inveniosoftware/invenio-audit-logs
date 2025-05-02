# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more details.

"""Component to add User data."""

from invenio_access.permissions import system_identity
from invenio_accounts.proxies import current_datastore
from invenio_records_resources.services.records.components import ServiceComponent


class UserContextComponent(ServiceComponent):
    """Service component to enrich audit log data with user data."""

    def create(self, identity, data=None, **kwargs):
        """Add user info."""
        if identity.id == system_identity.id:
            data["user"] = {
                "id": system_identity.id,
                "email": "system@system.org",
            }  # TODO: Remove this after confirming system user email is passed
        else:
            user = current_datastore.get_user(identity.id)
            user_blob = {"id": str(user.id), "email": user.email}
            if user.username:
                user_blob["name"] = user.username
            data["user"] = user_blob
