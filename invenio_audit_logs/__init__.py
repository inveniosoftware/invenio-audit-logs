# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
# Copyright (C) 2025-2026 Graz University of Technology.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Module providing audit logging features for Invenio.."""

from .ext import InvenioAuditLogs

__version__ = "1.0.0"

__all__ = (
    "__version__",
    "InvenioAuditLogs",
)
