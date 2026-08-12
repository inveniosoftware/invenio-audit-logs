# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-FileCopyrightText: 2025-2026 Graz University of Technology.
# SPDX-License-Identifier: MIT

"""Module providing audit logging features for Invenio.."""

from .ext import InvenioAuditLogs

__version__ = "3.0.2"

__all__ = (
    "__version__",
    "InvenioAuditLogs",
)
