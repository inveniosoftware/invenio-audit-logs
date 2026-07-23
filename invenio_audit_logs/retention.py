# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Retention policy resolver for audit logs.

The resolver maps an action id to a retention period and answers, for a given
reference time, whether the action is kept forever and the whole-month cutoff
before which its events have expired. It does no I/O so it can be unit tested in
isolation.
"""


class _KeepForever:
    """Sentinel marking an action whose events are never expired."""

    _instance = None

    def __new__(cls):
        """Return the single shared sentinel instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        """Return repr(self)."""
        return "KEEP_FOREVER"


KEEP_FOREVER = _KeepForever()
"""Retention value declaring that an action's events are kept forever."""


def _month_start(dt):
    """Return the first instant of ``dt``'s month, keeping its timezone."""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _subtract_months(dt, months):
    """Return ``dt`` shifted back by whole ``months``, wrapping across years."""
    total = dt.year * 12 + (dt.month - 1) - months
    year, month = divmod(total, 12)
    return dt.replace(year=year, month=month + 1)


class RetentionPolicy:
    """Resolve per-action retention periods to expiry cutoffs.

    Periods are configured as ``timedelta`` values and interpreted at whole-month
    granularity, aligned to the monthly storage. A period covers as many whole
    months as fit in its days, so 60 days keeps two months and 395 days keeps
    thirteen.
    """

    # Approximate a month as 30 days when reducing a timedelta to whole months.
    # The cutoff itself snaps to calendar-month boundaries, so this only decides
    # how many months a configured period covers.
    _days_per_month = 30

    def __init__(self, periods, default):
        """Build a resolver from a per-action mapping and a finite default."""
        self._periods = periods
        self._default = default

    @classmethod
    def from_config(cls, config):
        """Build a resolver from the application config mapping."""
        return cls(
            periods=config["AUDIT_LOGS_RETENTION"],
            default=config["AUDIT_LOGS_RETENTION_DEFAULT"],
        )

    def period(self, action):
        """Return the configured period for ``action`` or the default."""
        return self._periods.get(action, self._default)

    def is_kept_forever(self, action):
        """Whether ``action`` is exempt from expiry."""
        return self.period(action) is KEEP_FOREVER

    def cutoff(self, action, now):
        """Return the month boundary before which ``action`` events expired.

        Events with ``created`` strictly before the returned cutoff are expired.
        Returns ``None`` when the action is kept forever.
        """
        period = self.period(action)
        if period is KEEP_FOREVER:
            return None
        months = period.days // self._days_per_month
        return _subtract_months(_month_start(now), months)
