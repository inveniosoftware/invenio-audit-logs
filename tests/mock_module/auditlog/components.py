# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o.
# SPDX-License-Identifier: MIT
"""Test components."""

from invenio_records_resources.services.records.components import ServiceComponent


class CallTrackingComponent(ServiceComponent):
    """Test component.

    It does not modify the record, just tracks if it was called.
    """

    create_called = False
    read_called = False

    def create(self, identity, data, record=None, **kwargs):
        """Create action."""
        CallTrackingComponent.create_called = True

    def read(self, identity, record=None, **kwargs):
        """Read action."""
        CallTrackingComponent.read_called = True

    @classmethod
    def reset(cls):
        """Reset the component state."""
        CallTrackingComponent.create_called = False
        CallTrackingComponent.read_called = False
