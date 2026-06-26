#!/usr/bin/env python3
"""Generate thin dispatch run.py files for all 42 forge-agents × 4 frameworks.

Run from any directory:
    python agents/common/runners/_generate_dispatches.py

Each existing framework runner (langgraph/run.py, crewai/run.py,
claude_sdk/run.py, subagent/run.py) is REPLACED with a thin dispatcher that
delegates all framework boilerplate to the shared runners in common/runners/.
The original files are backed up to <file>.bak before overwriting.
"""
from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Agent config table
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentCfg:
    suffix: str                  # folder suffix after "api-tester-"
    harness_import: str          # e.g. "import pagination"
    harness_alias: str           # how the harness is referenced in code
    prompt_module: str           # e.g. "pagination_prompt"
    has_active_prompt: bool      # True for 39/42; False for old-style (1,3,5)
    brief_call: str              # e.g. "pagination.collection_brief(cfg)" or "" for precomputed
    param: str                   # generate() parameter name, e.g. "cfg"; "" for no-arg
    extract_fn: str              # "extract_json" or "extract_json_array"
    run_call: str                # full harness runner call with AGENT / generate
    print_stmt: str              # f-string body for the print line
    max_tokens: bool = False     # True for agents 10, 36
    token_tracking: bool = False # True for agents 7, 13
    multicaller: bool = False    # True for agents 11, 32, 37, 40
    # Derived flags
    precomputed_brief: bool = False   # generate(brief: str) -> no brief_call (agents 23, 34)
    no_arg_generate: bool = False     # generate() -> brief closed over (agent 5)
    list_extract: bool = False        # generate returns list (agent 42)


AGENTS: list[AgentCfg] = [
    # 1 – validate-request-payloads  (old-style, no active_prompt)
    AgentCfg(
        suffix="validate-request-payloads",
        harness_import="import contract",
        harness_alias="contract",
        prompt_module="prompt",
        has_active_prompt=False,
        brief_call="contract.endpoint_brief(endpoint)",
        param="endpoint",
        extract_fn="extract_json",
        run_call="contract.run_contract_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] payload_rejection_rate_pct={summary['payload_rejection_rate_pct']}% "
            "covered={summary['coverage']['covered']}/{summary['coverage']['applicable']}\""
        ),
    ),
    # 2 – verify-response-status-codes
    AgentCfg(
        suffix="verify-response-status-codes",
        harness_import="import status_contract",
        harness_alias="status_contract",
        prompt_module="status_prompt",
        has_active_prompt=True,
        brief_call="status_contract.operation_brief(op)",
        param="op",
        extract_fn="extract_json",
        run_call="status_contract.run_status_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] status_code_accuracy_rate_pct={summary['status_code_accuracy_rate_pct']}%\"",
    ),
    # 3 – check-authorization-rules  (old-style, no active_prompt)
    AgentCfg(
        suffix="check-authorization-rules",
        harness_import="import authz_contract",
        harness_alias="authz_contract",
        prompt_module="authz_prompt",
        has_active_prompt=False,
        brief_call="authz_contract.surface_brief(spec)",
        param="spec",
        extract_fn="extract_json",
        run_call="authz_contract.run_authz_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] access_control_accuracy_rate_pct={summary['access_control_accuracy_rate_pct']}% "
            "core_passed={summary['core_passed']}/{summary['core_sub_tests']}\""
        ),
    ),
    # 4 – test-pagination-behavior
    AgentCfg(
        suffix="test-pagination-behavior",
        harness_import="import pagination",
        harness_alias="pagination",
        prompt_module="pagination_prompt",
        has_active_prompt=True,
        brief_call="pagination.collection_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="pagination.run_pagination_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] correctness_rate={summary['pagination_correctness_rate_pct']}% "
            "scenarios={summary['scenarios_api_correct']}/{summary['scenarios_total']}\""
        ),
    ),
    # 5 – test-authentication-flows  (old-style, no-arg generate)
    AgentCfg(
        suffix="test-authentication-flows",
        harness_import="import auth_harness",
        harness_alias="auth_harness",
        prompt_module="auth_prompt",
        has_active_prompt=False,
        brief_call="",  # closed over
        param="",
        extract_fn="extract_json",
        run_call="auth_harness.run_auth_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] pass_rate={summary['auth_flow_pass_rate_pct']}% "
            "FAR={summary['false_acceptance_rate_pct']}% "
            "FRR={summary['false_rejection_rate_pct']}% "
            "executed={summary['executed_cases']}\""
        ),
        no_arg_generate=True,
    ),
    # 6 – validate-json-schema-responses
    AgentCfg(
        suffix="validate-json-schema-responses",
        harness_import="import schema_contract",
        harness_alias="schema_contract",
        prompt_module="schema_prompt",
        has_active_prompt=True,
        brief_call="schema_contract.endpoint_brief(op)",
        param="op",
        extract_fn="extract_json",
        run_call="schema_contract.run_schema_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] responses_validated={summary['responses_validated']} "
            "endpoints_covered={summary['endpoints_covered']}\""
        ),
    ),
    # 7 – validate-query-parameter-handling  (token tracking)
    AgentCfg(
        suffix="validate-query-parameter-handling",
        harness_import="import queryparam",
        harness_alias="queryparam",
        prompt_module="queryparam_prompt",
        has_active_prompt=True,
        brief_call="queryparam.collection_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="queryparam.run_queryparam_test(AGENT, generate, usage=lambda: TOTALS)",
        print_stmt=(
            "f\"[{AGENT}] accuracy={summary['query_param_handling_accuracy_pct']}% "
            "scenarios={summary['scenarios_api_correct']}/{summary['scenarios_total']} "
            "tokens={summary['tokens']['total_tokens']}\""
        ),
        token_tracking=True,
    ),
    # 8 – test-rate-limit-enforcement
    AgentCfg(
        suffix="test-rate-limit-enforcement",
        harness_import="import ratelimit",
        harness_alias="ratelimit",
        prompt_module="ratelimit_prompt",
        has_active_prompt=True,
        brief_call="ratelimit.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="ratelimit.run_ratelimit_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] rate_limit_contract_correctness_rate_pct={summary['rate_limit_contract_correctness_rate_pct']}%\"",
    ),
    # 9 – test-idempotency-of-endpoints
    AgentCfg(
        suffix="test-idempotency-of-endpoints",
        harness_import="import idempotency",
        harness_alias="idempotency",
        prompt_module="idempotency_prompt",
        has_active_prompt=True,
        brief_call="idempotency.collection_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="idempotency.run_idempotency_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] idempotency_compliance_rate_pct={summary['idempotency_compliance_rate_pct']}% "
            "idempotency_correctness_rate_pct={summary['idempotency_correctness_rate_pct']}%\""
        ),
    ),
    # 10 – validate-null-empty-fields  (max_tokens)
    AgentCfg(
        suffix="validate-null-empty-fields",
        harness_import="import null_contract",
        harness_alias="null_contract",
        prompt_module="null_prompt",
        has_active_prompt=True,
        brief_call="null_contract.endpoint_brief(ep)",
        param="ep",
        extract_fn="extract_json",
        run_call="null_contract.run_null_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] accuracy={summary['null_empty_validation_accuracy_pct']}% cases={summary['total_cases']}\"",
        max_tokens=True,
    ),
    # 11 – verify-content-type-negotiation  (multicaller)
    AgentCfg(
        suffix="verify-content-type-negotiation",
        harness_import="import cn",
        harness_alias="cn",
        prompt_module="cn_prompt",
        has_active_prompt=True,
        brief_call="cn.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="cn.run_cn_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] content_type_negotiation_accuracy_pct={summary['content_type_negotiation_accuracy_pct']}%\"",
        multicaller=True,
    ),
    # 12 – verify-error-message-clarity
    AgentCfg(
        suffix="verify-error-message-clarity",
        harness_import="import clarity_contract",
        harness_alias="clarity_contract",
        prompt_module="clarity_prompt",
        has_active_prompt=True,
        brief_call="clarity_contract.operation_brief(op)",
        param="op",
        extract_fn="extract_json",
        run_call="clarity_contract.run_clarity_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] error_clarity_pass_rate_pct={summary['error_clarity_pass_rate_pct']}% "
            "p1_security_defects={summary['p1_security_defects']}\""
        ),
    ),
    # 13 – validate-api-versioning-behavior  (token tracking)
    AgentCfg(
        suffix="validate-api-versioning-behavior",
        harness_import="import versioning",
        harness_alias="versioning",
        prompt_module="versioning_prompt",
        has_active_prompt=True,
        brief_call="versioning.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="versioning.run_versioning_test(AGENT, generate, usage=lambda: TOTALS)",
        print_stmt=(
            "f\"[{AGENT}] version_routing_accuracy_pct={summary['version_routing_accuracy_pct']}% "
            "tokens={summary['tokens']['total_tokens']}\""
        ),
        token_tracking=True,
    ),
    # 14 – test-webhook-delivery
    AgentCfg(
        suffix="test-webhook-delivery",
        harness_import="import webhook",
        harness_alias="webhook",
        prompt_module="webhook_prompt",
        has_active_prompt=True,
        brief_call="webhook.subject_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="webhook.run_webhook_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] webhook_contract_correctness_rate_pct={summary['webhook_contract_correctness_rate_pct']}% "
            "webhook_delivery_success_rate_pct={summary['webhook_delivery_success_rate_pct']}%\""
        ),
    ),
    # 15 – validate-header-propagation
    AgentCfg(
        suffix="validate-header-propagation",
        harness_import="import header",
        harness_alias="header",
        prompt_module="header_prompt",
        has_active_prompt=True,
        brief_call="header.endpoint_brief(endpoint)",
        param="endpoint",
        extract_fn="extract_json",
        run_call="header.run_header_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] header_propagation_rate_pct={summary['header_propagation_rate_pct']}%\"",
    ),
    # 16 – test-timeout-handling
    AgentCfg(
        suffix="test-timeout-handling",
        harness_import="import timeout as harness",
        harness_alias="harness",
        prompt_module="timeout_prompt",
        has_active_prompt=True,
        brief_call="harness.service_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="harness.run_timeout_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] timeout_enforcement_rate_pct={summary['timeout_enforcement_rate_pct']}%\"",
    ),
    # 17 – test-concurrent-request-handling
    AgentCfg(
        suffix="test-concurrent-request-handling",
        harness_import="import concurrency",
        harness_alias="concurrency",
        prompt_module="concurrency_prompt",
        has_active_prompt=True,
        brief_call="concurrency.brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="concurrency.run_concurrency_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] concurrent_request_success_rate_pct={summary['concurrent_request_success_rate_pct']}% "
            "db_count_delta={summary['db_count_delta']}\""
        ),
    ),
    # 18 – track-defect-density
    AgentCfg(
        suffix="track-defect-density",
        harness_import="import defectdensity",
        harness_alias="defectdensity",
        prompt_module="defectdensity_prompt",
        has_active_prompt=True,
        brief_call="defectdensity.sprint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="defectdensity.run_defectdensity_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] defect_density_report_accuracy_pct={summary['defect_density_report_accuracy_pct']}%\"",
    ),
    # 19 – verify-sorting-behavior
    AgentCfg(
        suffix="verify-sorting-behavior",
        harness_import="import sorting",
        harness_alias="sorting",
        prompt_module="sorting_prompt",
        has_active_prompt=True,
        brief_call="sorting.resource_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="sorting.run_sorting_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] sorting_accuracy_rate_pct={summary['sorting_accuracy_rate_pct']}%\"",
    ),
    # 20 – verify-crud-operation-integrity
    AgentCfg(
        suffix="verify-crud-operation-integrity",
        harness_import="import crud_contract",
        harness_alias="crud_contract",
        prompt_module="crud_prompt",
        has_active_prompt=True,
        brief_call="crud_contract.resource_brief(resource)",
        param="resource",
        extract_fn="extract_json",
        run_call="crud_contract.run_crud_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] crud_integrity_rate_pct={summary['crud_integrity_rate_pct']}%\"",
    ),
    # 21 – validate-search-and-filter-queries
    AgentCfg(
        suffix="validate-search-and-filter-queries",
        harness_import="import searchfilter",
        harness_alias="searchfilter",
        prompt_module="searchfilter_prompt",
        has_active_prompt=True,
        brief_call="searchfilter.collection_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="searchfilter.run_searchfilter_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] filter_accuracy_pct={summary['filter_accuracy_pct']}%\"",
    ),
    # 22 – verify-third-party-oauth-integration
    AgentCfg(
        suffix="verify-third-party-oauth-integration",
        harness_import="import oauth",
        harness_alias="oauth",
        prompt_module="oauth_prompt",
        has_active_prompt=True,
        brief_call="oauth.flow_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="oauth.run_oauth_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] oauth_flow_completion_rate_pct={summary['oauth_flow_completion_rate_pct']}%\"",
    ),
    # 23 – validate-correlation-id-propagation  (precomputed brief: str)
    AgentCfg(
        suffix="validate-correlation-id-propagation",
        harness_import="import cid",
        harness_alias="cid",
        prompt_module="cid_prompt",
        has_active_prompt=True,
        brief_call="",
        param="brief",
        extract_fn="extract_json",
        run_call="cid.run_cid_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] propagation_rate={summary['correlation_id_propagation_rate_pct']}% "
            "propagated={summary['scenarios_propagated']}/{summary['scenarios_total']}\""
        ),
        precomputed_brief=True,
    ),
    # 24 – test-ip-allowlist-enforcement
    AgentCfg(
        suffix="test-ip-allowlist-enforcement",
        harness_import="import ip_allowlist",
        harness_alias="ip_allowlist",
        prompt_module="ip_allowlist_prompt",
        has_active_prompt=True,
        brief_call="ip_allowlist.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="ip_allowlist.run_ip_allowlist_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] ip_allowlist_enforcement_rate_pct={summary['ip_allowlist_enforcement_rate_pct']}% "
            "any_nonallowlisted_200_bypass={summary['any_nonallowlisted_200_bypass']}\""
        ),
    ),
    # 25 – verify-caching-headers
    AgentCfg(
        suffix="verify-caching-headers",
        harness_import="import caching",
        harness_alias="caching",
        prompt_module="caching_prompt",
        has_active_prompt=True,
        brief_call="caching.collection_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="caching.run_caching_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] caching_header_compliance_rate_pct={summary['caching_header_compliance_rate_pct']}% "
            "caching_correctness_rate_pct={summary['caching_correctness_rate_pct']}%\""
        ),
    ),
    # 26 – run-regression-suite
    AgentCfg(
        suffix="run-regression-suite",
        harness_import="import regression",
        harness_alias="regression",
        prompt_module="regression_prompt",
        has_active_prompt=True,
        brief_call="regression.pair_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="regression.run_regression_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] regression_report_fidelity_pct={summary['regression_report_fidelity_pct']}% "
            "builds_that_must_block_deployment={summary['builds_that_must_block_deployment']}\""
        ),
    ),
    # 27 – test-file-upload-and-download
    AgentCfg(
        suffix="test-file-upload-and-download",
        harness_import="import upload",
        harness_alias="upload",
        prompt_module="upload_prompt",
        has_active_prompt=True,
        brief_call="upload.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="upload.run_upload_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] file_integrity_rate_pct={summary['file_integrity_rate_pct']}% "
            "over_size_rejection_rate_pct={summary['over_size_rejection_rate_pct']}% "
            "invalid_mime_rejection_rate_pct={summary['invalid_mime_rejection_rate_pct']}%\""
        ),
    ),
    # 28 – test-ssl-tls-enforcement
    AgentCfg(
        suffix="test-ssl-tls-enforcement",
        harness_import="import tls",
        harness_alias="tls",
        prompt_module="tls_prompt",
        has_active_prompt=True,
        brief_call="tls.target_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="tls.run_tls_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] tls_enforcement_rate_pct={summary['tls_enforcement_rate_pct']}%\"",
    ),
    # 29 – test-bulk-operation-endpoints
    AgentCfg(
        suffix="test-bulk-operation-endpoints",
        harness_import="import bulk",
        harness_alias="bulk",
        prompt_module="bulk_prompt",
        has_active_prompt=True,
        brief_call="bulk.brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="bulk.run_bulk_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] bulk_operation_accuracy_pct={summary['bulk_operation_accuracy_pct']}% "
            "mixed_db_delta={summary['mixed_db_delta']}\""
        ),
    ),
    # 30 – test-event-driven-api-triggers
    AgentCfg(
        suffix="test-event-driven-api-triggers",
        harness_import="import eventdriven",
        harness_alias="eventdriven",
        prompt_module="eventdriven_prompt",
        has_active_prompt=True,
        brief_call="eventdriven.topic_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="eventdriven.run_eventdriven_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] event_processing_success_rate_pct={summary['event_processing_success_rate_pct']}% "
            "dead_letter_queue_delivery_rate_pct={summary['dead_letter_queue_delivery_rate_pct']}%\""
        ),
    ),
    # 31 – verify-audit-log-generation
    AgentCfg(
        suffix="verify-audit-log-generation",
        harness_import="import auditlog",
        harness_alias="auditlog",
        prompt_module="auditlog_prompt",
        has_active_prompt=True,
        brief_call="auditlog.collection_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="auditlog.run_auditlog_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] audit_log_coverage_rate_pct={summary['audit_log_coverage_rate_pct']}% "
            "audit_correctness_rate_pct={summary['audit_correctness_rate_pct']}%\""
        ),
    ),
    # 32 – test-api-gateway-routing  (multicaller)
    AgentCfg(
        suffix="test-api-gateway-routing",
        harness_import="import routing",
        harness_alias="routing",
        prompt_module="routing_prompt",
        has_active_prompt=True,
        brief_call="routing.route_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="routing.run_routing_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] route_forwarding_accuracy={summary['route_forwarding_accuracy_pct']}% "
            "routes={summary['routes_forwarded']}/{summary['routes_total']}\""
        ),
        multicaller=True,
    ),
    # 33 – test-multipart-form-data-handling
    AgentCfg(
        suffix="test-multipart-form-data-handling",
        harness_import="import multipart as mp",
        harness_alias="mp",
        prompt_module="multipart_prompt",
        has_active_prompt=True,
        brief_call="mp.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="mp.run_multipart_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] multipart_handling_accuracy_pct={summary['multipart_handling_accuracy_pct']}%\"",
    ),
    # 34 – measure-api-consumer-satisfaction  (precomputed brief: str)
    AgentCfg(
        suffix="measure-api-consumer-satisfaction",
        harness_import="import nps",
        harness_alias="nps",
        prompt_module="nps_prompt",
        has_active_prompt=True,
        brief_call="",
        param="brief",
        extract_fn="extract_json",
        run_call="nps.run_nps_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] nps_score={summary['nps_score']} "
            "plan_accuracy_pct={summary['plan_accuracy_pct']}%\""
        ),
        precomputed_brief=True,
    ),
    # 35 – validate-retry-after-header-compliance
    AgentCfg(
        suffix="validate-retry-after-header-compliance",
        harness_import="import retryafter",
        harness_alias="retryafter",
        prompt_module="retryafter_prompt",
        has_active_prompt=True,
        brief_call="retryafter.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="retryafter.run_retryafter_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] retry_after_accuracy_pct={summary['retry_after_accuracy_pct']}% "
            "endpoints_honored={summary['endpoints_honored']} "
            "rate_limit_enforced={summary['rate_limit_enforced']}\""
        ),
    ),
    # 36 – verify-enum-value-restrictions  (max_tokens)
    AgentCfg(
        suffix="verify-enum-value-restrictions",
        harness_import="import enum_contract",
        harness_alias="enum_contract",
        prompt_module="enum_prompt",
        has_active_prompt=True,
        brief_call="enum_contract.endpoint_brief(ep)",
        param="ep",
        extract_fn="extract_json",
        run_call="enum_contract.run_enum_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] enum_validation_rate_pct={summary['enum_validation_rate_pct']}%\"",
        max_tokens=True,
    ),
    # 37 – test-soft-delete-behavior  (multicaller)
    AgentCfg(
        suffix="test-soft-delete-behavior",
        harness_import="import softdelete",
        harness_alias="softdelete",
        prompt_module="softdelete_prompt",
        has_active_prompt=True,
        brief_call="softdelete.brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="softdelete.run_softdelete_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] soft_delete_correctness_rate_pct={summary['soft_delete_correctness_rate_pct']}%\"",
        multicaller=True,
    ),
    # 38 – validate-graphql-depth-limits
    AgentCfg(
        suffix="validate-graphql-depth-limits",
        harness_import="import gqldepth",
        harness_alias="gqldepth",
        prompt_module="gqldepth_prompt",
        has_active_prompt=True,
        brief_call="gqldepth.endpoint_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="gqldepth.run_gqldepth_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] depth_enforcement_pct={summary['depth_enforcement_pct']}%\"",
    ),
    # 39 – test-long-polling-support
    AgentCfg(
        suffix="test-long-polling-support",
        harness_import="import longpoll as harness",
        harness_alias="harness",
        prompt_module="longpoll_prompt",
        has_active_prompt=True,
        brief_call="harness.channel_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="harness.run_longpoll_test(AGENT, generate)",
        print_stmt="f\"[{AGENT}] longpoll_response_accuracy_pct={summary['longpoll_response_accuracy_pct']}%\"",
    ),
    # 40 – create-postman-collection  (multicaller)
    AgentCfg(
        suffix="create-postman-collection",
        harness_import="import postman",
        harness_alias="postman",
        prompt_module="postman_prompt",
        has_active_prompt=True,
        brief_call="postman.brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="postman.run_postman_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] postman_coverage_rate_pct={summary['postman_coverage_rate_pct']}% "
            "newman_valid={summary['newman_valid']}\""
        ),
        multicaller=True,
    ),
    # 41 – run-cicd-pipeline
    AgentCfg(
        suffix="run-cicd-pipeline",
        harness_import="import cicd",
        harness_alias="cicd",
        prompt_module="cicd_prompt",
        has_active_prompt=True,
        brief_call="cicd.run_brief(cfg)",
        param="cfg",
        extract_fn="extract_json",
        run_call="cicd.run_cicd_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] pipeline_summary_fidelity_pct={summary['pipeline_summary_fidelity_pct']}% "
            "runs_that_must_block_deployment={summary['runs_that_must_block_deployment']}\""
        ),
    ),
    # 42 – test-case-creator  (list extract)
    AgentCfg(
        suffix="test-case-creator",
        harness_import="import testcase",
        harness_alias="testcase",
        prompt_module="testcase_prompt",
        has_active_prompt=True,
        brief_call="testcase.agent_brief(cfg)",
        param="cfg",
        extract_fn="extract_json_array",
        run_call="testcase.run_testcase_test(AGENT, generate)",
        print_stmt=(
            "f\"[{AGENT}] coverage_rate={summary['test_case_coverage_rate_pct']}% "
            "field_accuracy={summary['test_case_field_accuracy_pct']}% "
            "cases={summary['present_tc']}/{summary['gold_tc']}\""
        ),
        list_extract=True,
    ),
]

# ──────────────────────────────────────────────────────────────────────────────
# Code-generation helpers
# ──────────────────────────────────────────────────────────────────────────────

FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "subagent"]

RUNNER_IMPORT = {
    "langgraph": "from runners.langgraph_runner import build_invoker",
    "crewai":    "from runners.crewai_runner import build_invoker",
    "claude_sdk": "from runners.claude_sdk_runner import build_invoker",
    "subagent":  "from runners.subagent_runner import build_invoker",
}

AGENT_STRING = {
    "langgraph":  "langgraph",
    "crewai":     "crewai",
    "claude_sdk": "claude_sdk",
    "subagent":   "api-tester-{suffix}",  # subagent keeps full agent name
}


def _agent_folder(suffix: str) -> str:
    return f"api-tester-{suffix}"


def _subagent_md(suffix: str) -> str:
    return f'Path(__file__).resolve().parents[1] / "subagent" / "api-tester-{suffix}.md"'


def _prompt_import(cfg: AgentCfg) -> str:
    if cfg.has_active_prompt:
        return f"from {cfg.prompt_module} import active_prompt, user_message"
    return f"from {cfg.prompt_module} import user_message"


def _system_load(cfg: AgentCfg, framework: str) -> str:
    """Return the system-prompt loading lines for the given framework."""
    if framework == "subagent":
        # subagent always reads from .md (active_prompt is not used)
        return "system = load_system_prompt(SUBAGENT_MD)"
    if cfg.has_active_prompt:
        return "system = load_system_prompt(SUBAGENT_MD, active_prompt)"
    return "system = load_system_prompt(SUBAGENT_MD)"


def _build_invoker_call(cfg: AgentCfg, framework: str) -> str:
    if framework == "langgraph":
        parts = ["WS", "system", "user_message"]
        if cfg.max_tokens:
            parts.append("max_tokens=int(os.environ.get('FORGE_MAX_TOKENS', '8192'))")
        if cfg.multicaller:
            parts.append("multicaller=True")
        if cfg.token_tracking:
            parts.append("on_usage=_add_usage")
        return f"invoke = build_invoker({', '.join(parts)})"
    return "invoke = build_invoker(WS, system, user_message)"


def _generate_fn_block(cfg: AgentCfg) -> str:
    """Return the generate() function definition."""
    if cfg.no_arg_generate:
        # Agent 5: brief pre-fetched, generate() closes over it
        return textwrap.dedent("""\
            brief = {harness}.scheme_brief()

            def generate() -> dict:
                return {harness}.{extract_fn}(invoke(brief)) or {{}}
        """).format(harness=cfg.harness_alias, extract_fn=cfg.extract_fn)

    if cfg.precomputed_brief:
        # Agents 23, 34: harness passes brief str directly
        return_type = "list" if cfg.list_extract else "dict"
        empty = "[]" if cfg.list_extract else "{}"
        return textwrap.dedent("""\
            def generate(brief: str) -> {return_type}:
                return {harness}.{extract_fn}(invoke(brief)) or {empty}
        """).format(
            return_type=return_type,
            harness=cfg.harness_alias,
            extract_fn=cfg.extract_fn,
            empty=empty,
        )

    return_type = "list" if cfg.list_extract else "dict"
    empty = "[]" if cfg.list_extract else "{}"
    return textwrap.dedent("""\
        def generate({param}: dict) -> {return_type}:
            brief = {brief_call}
            return {harness}.{extract_fn}(invoke(brief)) or {empty}
    """).format(
        param=cfg.param,
        return_type=return_type,
        brief_call=cfg.brief_call,
        harness=cfg.harness_alias,
        extract_fn=cfg.extract_fn,
        empty=empty,
    )


def _token_tracking_block() -> str:
    return textwrap.dedent("""\
        TOTALS: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


        def _add_usage(meta: dict | None) -> None:
            if not meta:
                return
            TOTALS["prompt_tokens"] += int(meta.get("input_tokens", 0) or 0)
            TOTALS["completion_tokens"] += int(meta.get("output_tokens", 0) or 0)
            TOTALS["total_tokens"] += int(meta.get("total_tokens", 0) or 0)

    """)


def render_dispatch(cfg: AgentCfg, framework: str) -> str:
    """Render a complete thin-dispatch run.py for one agent × framework."""
    suffix = cfg.suffix
    agent_name = _agent_folder(suffix)
    agent_str = AGENT_STRING[framework].format(suffix=suffix)

    needs_os = cfg.max_tokens
    imports_head = "#!/usr/bin/env python3\n"
    imports_head += f'"""Thin dispatcher: {framework} runner for {agent_name}.\n\n'
    imports_head += f"Delegates all framework boilerplate to common/runners/{framework}_runner.py.\n"
    imports_head += '"""\n'
    imports_head += "from __future__ import annotations\n\n"

    std_imports = ["import sys"]
    if needs_os:
        std_imports.insert(0, "import os")
    imports_head += "\n".join(std_imports) + "\n"
    imports_head += "from pathlib import Path\n\n"

    imports_head += (
        f"WS = Path(os.environ.get('FORGE_WORKSPACE', Path(__file__).resolve().parents[3]))\n"
        if needs_os
        else "WS = Path(\n    os.environ.get('FORGE_WORKSPACE', str(Path(__file__).resolve().parents[3]))\n)\n"
    )
    # Simpler WS for most agents
    imports_head = (
        "#!/usr/bin/env python3\n"
        f'"""Thin dispatcher: {framework} runner for {agent_name}.\n\n'
        f"Delegates all framework boilerplate to common/runners/{framework}_runner.py.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
    )
    if needs_os:
        imports_head += "import os\n"
    imports_head += "import sys\n"
    imports_head += "from pathlib import Path\n\n"
    imports_head += "WS = Path(os.environ.get(\"FORGE_WORKSPACE\", str(Path(__file__).resolve().parents[3])))\n" if needs_os else \
                    "import os\nWS = Path(os.environ.get(\"FORGE_WORKSPACE\", str(Path(__file__).resolve().parents[3])))\n"

    # Build the file cleanly
    lines: list[str] = [
        "#!/usr/bin/env python3",
        f'"""Thin dispatcher: {framework} runner for {agent_name}.',
        "",
        f"Delegates all framework boilerplate to common/runners/{framework}_runner.py.",
        '"""',
        "from __future__ import annotations",
        "",
        "import os",
        "import sys",
        "from pathlib import Path",
        "",
        'WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[3])))',
        "sys.path.insert(0, str(WS / \"agents\" / \"common\"))",
        "sys.path.insert(0, str(WS / \"scripts\"))",
        "",
        cfg.harness_import + "  # noqa: E402",
        _prompt_import(cfg) + "  # noqa: E402",
        f"from runners.utils import load_system_prompt  # noqa: E402",
        RUNNER_IMPORT[framework] + "  # noqa: E402",
        "",
        f'AGENT = "{agent_str}"',
        f"SUBAGENT_MD = {_subagent_md(suffix)}",
    ]

    if cfg.token_tracking:
        lines += ["", ""]
        lines += _token_tracking_block().splitlines()

    lines += [
        "",
        "",
        "def main() -> None:",
    ]

    # system load
    lines.append(f"    {_system_load(cfg, framework)}")

    # build_invoker
    lines.append(f"    {_build_invoker_call(cfg, framework)}")
    lines.append("")

    # generate function (indented into main)
    gen_block = _generate_fn_block(cfg)
    for gline in gen_block.splitlines():
        lines.append("    " + gline if gline else "")

    lines.append("")

    # harness run call
    lines.append(f"    summary = {cfg.run_call}")

    # print
    lines.append(f"    print({cfg.print_stmt})")

    lines += [
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# File writer
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    here = Path(__file__).resolve()
    # common/runners/_generate_dispatches.py  →  agents/
    agents_dir = here.parents[2]

    written = 0
    skipped = 0
    backed_up = 0

    for cfg in AGENTS:
        folder = agents_dir / _agent_folder(cfg.suffix)
        if not folder.exists():
            print(f"  SKIP (folder missing): {folder.name}")
            skipped += 1
            continue

        for fw in FRAMEWORKS:
            fw_dir = folder / fw
            if not fw_dir.exists():
                print(f"  SKIP (subdir missing): {folder.name}/{fw}")
                skipped += 1
                continue

            run_py = fw_dir / "run.py"
            if run_py.exists():
                bak = run_py.with_suffix(".py.bak")
                run_py.rename(bak)
                backed_up += 1

            content = render_dispatch(cfg, fw)
            run_py.write_text(content)
            written += 1

    print(f"\nDone. {written} files written, {backed_up} backed up, {skipped} skipped.")


if __name__ == "__main__":
    main()
