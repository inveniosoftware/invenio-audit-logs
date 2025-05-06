# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Invenio-Audit-Logs Permissions Generators."""

from flask_login import current_user
from flask_principal import UserNeed
from invenio_access.permissions import system_process
from invenio_records_permissions.generators import Generator


# Permission generator to check if the user identity matches the identity in the request
class CurrentUser(Generator):
    """Check if the user identity matches the identity in the request."""

    def needs(self, identity=None, **kwargs):
        """Check if the user identity matches the identity in the request."""
        if identity:
            return [UserNeed(current_user.id)]
        return [system_process]
