# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit Logs Service Config."""

from invenio_i18n import lazy_gettext as _
from invenio_indexer.api import RecordIndexer
from invenio_records_resources.services import EndpointLink, pagination_endpoint_links
from invenio_records_resources.services.base import ServiceConfig
from invenio_records_resources.services.base.config import ConfiguratorMixin, FromConfig
from invenio_records_resources.services.records.config import (
    SearchOptions as SearchOptionsBase,
)
from invenio_records_resources.services.records.facets import TermsFacet
from invenio_records_resources.services.records.params import (
    FacetsParam,
    PaginationParam,
    QueryStrParam,
    SortParam,
)
from invenio_records_resources.services.records.queryparser import QueryParser

from ..proxies import current_audit_logs_actions_registry
from ..records import AuditLog
from . import results
from .permissions import AuditLogPermissionPolicy
from .schema import AuditLogSchema


class AuditLogSearchOptions(SearchOptionsBase):
    """Audit log search options."""

    sort_default = "newest"
    sort_default_no_query = "newest"

    query_parser_cls = QueryParser.factory(
        fields=[
            "id",
            "action",
            "user.id",
            "user.username",
            "user.email",
            "user.email.keyword",
            "resource.id",
            "resource.type",
        ]
    )

    sort_options = {
        "bestmatch": dict(title=_("Best match"), fields=["_score"]),
        "newest": dict(title=_("Newest"), fields=["-@timestamp"]),
        "oldest": dict(title=_("Oldest"), fields=["@timestamp"]),
    }

    facets = {
        "resource": TermsFacet(
            field="resource.type",
            label="Resource",
            value_labels={"record": "Record", "community": "Community"},
        ),
        "action_name": TermsFacet(
            field="action",
            label="Action",
            value_labels=lambda keys: {
                k: current_audit_logs_actions_registry[k].id for k in keys
            },
        ),
    }

    pagination_options = {"default_results_per_page": 20, "default_max_results": 1000}

    params_interpreters_cls = [
        QueryStrParam,
        SortParam,
        PaginationParam,
        FacetsParam,
    ]


class AuditLogServiceConfig(ServiceConfig, ConfiguratorMixin):
    """Audit log service configuration."""

    enabled = FromConfig("AUDIT_LOGS_ENABLED", default=True)
    service_id = "audit-logs"
    permission_policy_cls = FromConfig(
        "AUDIT_LOGS_PERMISSION_POLICY",
        default=AuditLogPermissionPolicy,
    )
    search = AuditLogSearchOptions
    schema = AuditLogSchema

    record_cls = AuditLog
    indexer_cls = RecordIndexer
    indexer_queue_name = service_id
    index_dumper = None

    components = []
    links_item = {
        "self": EndpointLink(
            "audit_logs.read",
            vars=lambda obj, vars: vars.update(id=obj.id),
            params=["id"],
        ),
    }
    links_search = pagination_endpoint_links("audit_logs.search")

    result_item_cls = results.AuditLogItem
    result_list_cls = results.AuditLogList
