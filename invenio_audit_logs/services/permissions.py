# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit Logs Service Permissions."""

from invenio_administration.generators import Administration
from invenio_records_permissions.generators import Disable, SystemProcess
from invenio_records_permissions.policies import BasePermissionPolicy


class AuditLogPermissionPolicy(BasePermissionPolicy):
    """Permission policy for audit logs."""

    can_search = [Administration(), SystemProcess()]
    can_create = [SystemProcess()]
    can_read = [Administration(), SystemProcess()]
    can_update = [Disable()]
    can_delete = [Disable()]
