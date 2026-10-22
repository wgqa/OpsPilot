from __future__ import annotations

import hmac
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal


Scenario = Literal[
    "S1_POS",
    "S1_DISABLED",
    "S2_SCOPE_DENIED",
    "S2_SCOPE_ALLOWED",
    "S2_INVALID_CREDENTIAL",
    "S2_RESOURCE_HIDDEN",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS credentials (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    credential_ref TEXT NOT NULL,
    secret_value TEXT NOT NULL,
    credential_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, credential_ref)
);
CREATE TABLE IF NOT EXISTS principals (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    principal_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ENABLED', 'DISABLED')),
    principal_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, principal_id)
);
CREATE TABLE IF NOT EXISTS integrations (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    credential_ref TEXT NOT NULL,
    config_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, integration_id),
    FOREIGN KEY (tenant_id, principal_id)
        REFERENCES principals(tenant_id, principal_id),
    FOREIGN KEY (tenant_id, credential_ref)
        REFERENCES credentials(tenant_id, credential_ref)
);
CREATE TABLE IF NOT EXISTS services (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    route TEXT NOT NULL,
    PRIMARY KEY (tenant_id, service_id),
    FOREIGN KEY (tenant_id, integration_id)
        REFERENCES integrations(tenant_id, integration_id)
);
CREATE TABLE IF NOT EXISTS auth_policies (
    tenant_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    accepted_credential_ref TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, service_id),
    FOREIGN KEY (tenant_id, service_id)
        REFERENCES services(tenant_id, service_id),
    FOREIGN KEY (tenant_id, accepted_credential_ref)
        REFERENCES credentials(tenant_id, credential_ref)
);
CREATE TABLE IF NOT EXISTS orders (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
CREATE TABLE IF NOT EXISTS auth_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    route TEXT NOT NULL,
    result_code TEXT NOT NULL,
    credential_policy_version INTEGER,
    request_id TEXT,
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS principal_scope_grants (
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    granted_scopes_json TEXT NOT NULL,
    grant_version INTEGER NOT NULL CHECK (grant_version >= 1),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (tenant_id, principal_id)
        REFERENCES principals(tenant_id, principal_id)
);
CREATE TABLE IF NOT EXISTS route_scope_policies (
    tenant_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    route TEXT NOT NULL,
    required_scopes_json TEXT NOT NULL,
    scope_policy_version INTEGER NOT NULL CHECK (scope_policy_version >= 1),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, service_id, route),
    FOREIGN KEY (tenant_id, service_id)
        REFERENCES services(tenant_id, service_id)
);
CREATE TABLE IF NOT EXISTS authz_events (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    authn_event_id INTEGER NOT NULL REFERENCES auth_events(event_id),
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    route TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('ALLOW', 'DENY')),
    reason_code TEXT NOT NULL,
    credential_policy_version INTEGER NOT NULL,
    scope_policy_version INTEGER NOT NULL,
    grant_version INTEGER NOT NULL,
    required_scopes_json TEXT NOT NULL,
    granted_scopes_json TEXT NOT NULL,
    missing_scopes_json TEXT NOT NULL,
    resource_binding_valid INTEGER NOT NULL CHECK (resource_binding_valid IN (0, 1)),
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_authz_events_scope
    ON authz_events (tenant_id, principal_id, service_id, observed_at);
CREATE TABLE IF NOT EXISTS thread_owners (
    thread_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    owner_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trusted_operators (
    actor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    role TEXT NOT NULL CHECK (role IN ('SUPPORT', 'APPROVER'))
);
CREATE TABLE IF NOT EXISTS task_bindings (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    actor_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_id, tenant_id),
    FOREIGN KEY (tenant_id, service_id) REFERENCES services(tenant_id, service_id),
    FOREIGN KEY (tenant_id, integration_id) REFERENCES integrations(tenant_id, integration_id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES principals(tenant_id, principal_id)
);
CREATE TABLE IF NOT EXISTS task_controls (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    terminal_state TEXT NOT NULL CHECK (terminal_state IN ('ACTIVE', 'ABORTED')),
    control_revision INTEGER NOT NULL CHECK (control_revision >= 0),
    pending_critical_message_seq INTEGER,
    applied_critical_message_seq INTEGER NOT NULL DEFAULT 0,
    changed_at TEXT NOT NULL,
    changed_by TEXT,
    reason TEXT,
    UNIQUE (task_id, tenant_id),
    FOREIGN KEY (task_id, tenant_id)
        REFERENCES task_bindings(task_id, tenant_id) ON DELETE CASCADE,
    CHECK (pending_critical_message_seq IS NULL OR pending_critical_message_seq > applied_critical_message_seq)
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    owner_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (session_id, tenant_id)
);
CREATE INDEX IF NOT EXISTS ix_sessions_owner ON sessions(tenant_id, owner_id, updated_at);
CREATE TABLE IF NOT EXISTS session_task_links (
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    PRIMARY KEY (session_id, task_id),
    UNIQUE (task_id),
    FOREIGN KEY (session_id, tenant_id) REFERENCES sessions(session_id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id, tenant_id) REFERENCES task_bindings(task_id, tenant_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS commands (
    command_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    command_kind TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    accepted_status TEXT NOT NULL CHECK (accepted_status IN ('ACCEPTED', 'REJECTED')),
    error_code TEXT,
    message_id TEXT,
    run_id TEXT,
    result_json TEXT NOT NULL,
    UNIQUE (tenant_id, actor_id, command_kind, target_ref, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_commands_task ON commands(tenant_id, target_ref, accepted_at);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    task_id TEXT,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    role TEXT NOT NULL CHECK (role IN ('USER', 'ASSISTANT', 'SYSTEM')),
    input_kind TEXT NOT NULL CHECK (input_kind IN ('CHAT_READONLY', 'CORRECT_TASK_INPUT')),
    body TEXT NOT NULL,
    body_digest TEXT NOT NULL,
    command_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    application_state TEXT NOT NULL DEFAULT 'RECEIVED_NOT_APPLIED'
        CHECK (application_state IN ('RECEIVED_NOT_APPLIED', 'APPLIED_TO_RUN')),
    applied_run_id TEXT,
    UNIQUE (session_id, sequence),
    UNIQUE (message_id, task_id, sequence),
    FOREIGN KEY (session_id, tenant_id) REFERENCES sessions(session_id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id, tenant_id) REFERENCES task_bindings(task_id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_messages_task_seq ON messages(task_id, sequence);
CREATE TABLE IF NOT EXISTS task_runs (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT,
    session_id TEXT NOT NULL,
    command_id TEXT NOT NULL UNIQUE,
    source_message_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('CHAT_READONLY', 'INVESTIGATE', 'RESUME', 'APPROVAL_RESUME', 'RECONCILE')),
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'WAITING_INPUT', 'WAITING_APPROVAL', 'INTERRUPTED_RECOVERABLE')),
    control_revision_at_start INTEGER,
    expected_control_revision INTEGER,
    consumed_message_seq INTEGER NOT NULL DEFAULT 0,
    applied_critical_message_seq INTEGER NOT NULL DEFAULT 0,
    blocked_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    FOREIGN KEY (task_id, tenant_id) REFERENCES task_bindings(task_id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id, tenant_id) REFERENCES sessions(session_id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (source_message_id, task_id, consumed_message_seq)
        REFERENCES messages(message_id, task_id, sequence) DEFERRABLE INITIALLY DEFERRED
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_task_runs_one_active_business
    ON task_runs(task_id) WHERE status = 'RUNNING' AND kind != 'CHAT_READONLY' AND task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_task_runs_queue ON task_runs(status, created_at);
CREATE TABLE IF NOT EXISTS task_run_inputs (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    input_digest TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance = 'USER_INPUT_UNTRUSTED'),
    consumed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS domain_outbox (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT,
    session_id TEXT,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (source_kind, source_id, event_kind)
);
CREATE INDEX IF NOT EXISTS ix_domain_outbox_task ON domain_outbox(tenant_id, task_id, created_at);
CREATE TABLE IF NOT EXISTS web_auth_sessions (
    token_digest TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    role TEXT NOT NULL CHECK (role IN ('SUPPORT', 'APPROVER')),
    csrf_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_web_auth_sessions_expiry ON web_auth_sessions(expires_at, revoked_at);
CREATE TABLE IF NOT EXISTS session_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    happened_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (source_kind, source_id, event_kind),
    FOREIGN KEY (session_id, tenant_id) REFERENCES sessions(session_id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_session_events_cursor ON session_events(session_id, event_seq);
CREATE TABLE IF NOT EXISTS web_worker_state (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    owner_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    epoch INTEGER NOT NULL CHECK (epoch > 0),
    acquired_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_execution_budgets (
    task_id TEXT PRIMARY KEY REFERENCES task_bindings(task_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    active_elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK (active_elapsed_ms >= 0),
    active_started_at TEXT,
    heartbeat_at TEXT,
    deadline_ms INTEGER NOT NULL CHECK (deadline_ms > 0),
    deadline_reached_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (task_id, tenant_id) REFERENCES task_bindings(task_id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_task_execution_budget_tenant ON task_execution_budgets(tenant_id, task_id);
CREATE TABLE IF NOT EXISTS d2_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    run_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('MODEL', 'MCP')),
    call_id TEXT NOT NULL,
    tool_call_id TEXT,
    tool_name TEXT,
    argument_digest TEXT,
    status TEXT NOT NULL DEFAULT 'RESERVED',
    reserved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    result_digest TEXT,
    error_class TEXT
);
CREATE INDEX IF NOT EXISTS ix_d2_attempts_task_kind ON d2_attempts(task_id, kind);
CREATE TABLE IF NOT EXISTS d2_model_traces (
    call_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    attempt_id TEXT NOT NULL REFERENCES d2_attempts(attempt_id),
    model_id TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    input_evidence_ids_json TEXT NOT NULL,
    provider_response_id TEXT,
    tool_calls_json TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    usage_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS d2_pending_tool_calls (
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    call_id TEXT NOT NULL REFERENCES d2_model_traces(call_id),
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (task_id, call_id, tool_call_id)
);
CREATE TABLE IF NOT EXISTS d2_tool_observations (
    observation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    call_id TEXT NOT NULL,
    attempt_id TEXT,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    argument_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_added INTEGER NOT NULL,
    error_class TEXT,
    result_digest TEXT,
    result_json TEXT,
    evidence_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_d2_observations_task ON d2_tool_observations(task_id, created_at);
CREATE TABLE IF NOT EXISTS d2_evidence (
    evidence_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    call_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    principal_id TEXT,
    data_source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    observed_versions_json TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    original_result_ref TEXT NOT NULL,
    trust_class TEXT NOT NULL,
    digest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_d2_evidence_task_fact ON d2_evidence(task_id, fact_type, fetched_at);
CREATE TABLE IF NOT EXISTS d2_reports (
    report_ref TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES task_bindings(task_id),
    content_digest TEXT NOT NULL,
    immutable_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS s2_gate_traces (
    trace_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    run_id TEXT REFERENCES task_runs(run_id),
    decision TEXT NOT NULL CHECK (decision IN ('NOT_APPLICABLE', 'DIAGNOSED', 'NEED_MORE', 'NO_ACTION', 'INCONCLUSIVE')),
    reason_code TEXT NOT NULL,
    request_id TEXT,
    decision_id INTEGER,
    evidence_ids_json TEXT NOT NULL,
    evidence_digests_json TEXT NOT NULL,
    predicate_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_s2_gate_trace_task ON s2_gate_traces(task_id, created_at);
CREATE TABLE IF NOT EXISTS s2_diagnosis_receipts (
    receipt_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    run_id TEXT NOT NULL REFERENCES task_runs(run_id),
    request_id TEXT NOT NULL,
    decision_id INTEGER NOT NULL,
    gate_policy_version TEXT NOT NULL,
    predicate_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    evidence_digests_json TEXT NOT NULL,
    observed_versions_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, run_id, request_id)
);
CREATE INDEX IF NOT EXISTS ix_s2_receipt_task ON s2_diagnosis_receipts(task_id, created_at);
CREATE TABLE IF NOT EXISTS s2_handoff_drafts (
    draft_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    receipt_id TEXT NOT NULL REFERENCES s2_diagnosis_receipts(receipt_id),
    version INTEGER NOT NULL CHECK (version > 0),
    content_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, receipt_id),
    UNIQUE (tenant_id, task_id, version)
);
CREATE INDEX IF NOT EXISTS ix_s2_draft_task ON s2_handoff_drafts(task_id, version);
CREATE TABLE IF NOT EXISTS s2_handoff_queue_entries (
    entry_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    handoff_kind TEXT NOT NULL CHECK (handoff_kind = 'SCOPE_REVIEW'),
    receiver_queue_id TEXT NOT NULL,
    receiver_identity_ref TEXT NOT NULL,
    draft_id TEXT NOT NULL REFERENCES s2_handoff_drafts(draft_id),
    draft_version INTEGER NOT NULL CHECK (draft_version > 0),
    draft_digest TEXT NOT NULL,
    received_at TEXT NOT NULL,
    review_due_at TEXT NOT NULL,
    queue_status TEXT NOT NULL CHECK (queue_status IN ('PENDING_REVIEW', 'REVIEWED')),
    UNIQUE (tenant_id, task_id, handoff_kind),
    UNIQUE (entry_id, tenant_id, task_id),
    FOREIGN KEY (task_id, tenant_id) REFERENCES task_bindings(task_id, tenant_id)
);
CREATE INDEX IF NOT EXISTS ix_s2_handoff_queue_status ON s2_handoff_queue_entries(queue_status, review_due_at);
CREATE TABLE IF NOT EXISTS s2_handoff_receipts (
    receipt_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    handoff_kind TEXT NOT NULL CHECK (handoff_kind = 'SCOPE_REVIEW'),
    entry_id TEXT NOT NULL UNIQUE,
    draft_id TEXT NOT NULL,
    draft_version INTEGER NOT NULL CHECK (draft_version > 0),
    draft_digest TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    canonical_request_digest TEXT NOT NULL,
    accepted_by_receiver_ref TEXT NOT NULL,
    accepted_by_actor_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    accepted_at TEXT NOT NULL,
    receipt_digest TEXT NOT NULL,
    control_revision INTEGER NOT NULL CHECK (control_revision >= 0),
    request_id TEXT NOT NULL,
    decision_id INTEGER NOT NULL,
    credential_policy_version INTEGER NOT NULL,
    scope_policy_version INTEGER NOT NULL,
    grant_version INTEGER NOT NULL,
    UNIQUE (tenant_id, task_id, handoff_kind),
    FOREIGN KEY (entry_id, tenant_id, task_id)
        REFERENCES s2_handoff_queue_entries(entry_id, tenant_id, task_id)
);
CREATE INDEX IF NOT EXISTS ix_s2_handoff_receipt_task ON s2_handoff_receipts(tenant_id, task_id, accepted_at);
CREATE TRIGGER IF NOT EXISTS trg_s2_handoff_receipt_no_update
BEFORE UPDATE ON s2_handoff_receipts
BEGIN
    SELECT RAISE(ABORT, 'S2 HandoffReceipt is immutable');
END;
CREATE TRIGGER IF NOT EXISTS trg_s2_handoff_receipt_no_delete
BEFORE DELETE ON s2_handoff_receipts
BEGIN
    SELECT RAISE(ABORT, 'S2 HandoffReceipt is immutable');
END;
CREATE TABLE IF NOT EXISTS d2_tool_faults (
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    tool_name TEXT NOT NULL,
    remaining_calls INTEGER NOT NULL,
    error_code TEXT NOT NULL,
    PRIMARY KEY (task_id, tool_name)
);
CREATE TABLE IF NOT EXISTS executor_services (
    executor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS tickets (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    ticket_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    PRIMARY KEY (tenant_id, ticket_id)
);
CREATE TABLE IF NOT EXISTS d3_plans (
    plan_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    plan_version INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    plan_signature TEXT NOT NULL,
    canonical_plan_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, task_id, plan_hash),
    UNIQUE (tenant_id, task_id, plan_signature),
    UNIQUE (tenant_id, task_id, plan_version)
);
CREATE TABLE IF NOT EXISTS d3_plan_control_bindings (
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    bound_control_revision INTEGER NOT NULL CHECK (bound_control_revision >= 0),
    consumed_message_seq INTEGER NOT NULL DEFAULT 0,
    task_run_id TEXT REFERENCES task_runs(run_id),
    bound_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, task_id, plan_hash),
    FOREIGN KEY (tenant_id, task_id, plan_hash)
        REFERENCES d3_plans(tenant_id, task_id, plan_hash) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS d3_plan_authorizations (
    plan_hash TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    eligibility TEXT NOT NULL CHECK (eligibility IN ('ACTIVE', 'SUPERSEDED', 'CANCELLED')),
    generation INTEGER NOT NULL,
    changed_by TEXT,
    change_reason TEXT,
    active_from TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_d3_plan_auth_task ON d3_plan_authorizations(tenant_id, task_id, eligibility);
CREATE TABLE IF NOT EXISTS d3_plan_authorization_history (
    history_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    eligibility TEXT NOT NULL CHECK (eligibility IN ('ACTIVE', 'SUPERSEDED', 'CANCELLED')),
    generation INTEGER NOT NULL,
    changed_by TEXT,
    change_reason TEXT,
    changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d3_approvals (
    approval_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    approver_id TEXT NOT NULL,
    approval_scope_json TEXT NOT NULL,
    approved_plan_digest TEXT NOT NULL,
    target_resource_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    action_kinds_json TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    decided_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash)
);
CREATE TABLE IF NOT EXISTS approval_resume_links (
    approval_id TEXT PRIMARY KEY REFERENCES d3_approvals(approval_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    source_investigation_run_id TEXT NOT NULL REFERENCES task_runs(run_id),
    source_checkpoint_thread_id TEXT NOT NULL,
    resume_run_id TEXT NOT NULL UNIQUE REFERENCES task_runs(run_id),
    control_revision INTEGER NOT NULL CHECK (control_revision >= 0),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash),
    FOREIGN KEY (tenant_id, task_id, plan_hash)
        REFERENCES d3_plans(tenant_id, task_id, plan_hash) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_approval_resume_task ON approval_resume_links(tenant_id, task_id, created_at);
CREATE TABLE IF NOT EXISTS d3_action_permissions (
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    approval_id TEXT NOT NULL REFERENCES d3_approvals(approval_id),
    action_kind TEXT NOT NULL CHECK (action_kind IN ('REPAIR', 'DELIVER')),
    state TEXT NOT NULL CHECK (state IN ('AVAILABLE', 'CONSUMED', 'REVOKED')),
    used_by_action_id TEXT,
    changed_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, task_id, plan_hash, action_kind)
);
CREATE TABLE IF NOT EXISTS d3_action_intents (
    action_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    action_kind TEXT NOT NULL CHECK (action_kind IN ('REPAIR', 'DELIVER')),
    idempotency_key TEXT NOT NULL UNIQUE,
    approval_id TEXT NOT NULL,
    canonical_request_json TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, action_kind)
);
CREATE TABLE IF NOT EXISTS d3_action_ledgers (
    ledger_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    action_kind TEXT NOT NULL CHECK (action_kind IN ('REPAIR', 'DELIVER')),
    action_id TEXT NOT NULL UNIQUE REFERENCES d3_action_intents(action_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMMITTED', 'REJECTED_PRECONDITION', 'REJECTED_AUTH')),
    before_version INTEGER,
    after_version INTEGER,
    result_json TEXT NOT NULL,
    result_digest TEXT NOT NULL,
    committed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d3_verification_receipts (
    verification_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    repair_action_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    business_route TEXT NOT NULL,
    probe_observed_versions_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    response_status INTEGER NOT NULL,
    business_assertions_json TEXT NOT NULL,
    recovery_verified INTEGER NOT NULL CHECK (recovery_verified IN (0, 1)),
    result_digest TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, repair_action_id)
);
CREATE TABLE IF NOT EXISTS d3_report_artifacts (
    report_ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    repair_action_id TEXT NOT NULL,
    verification_id TEXT NOT NULL,
    report_version INTEGER NOT NULL,
    content_digest TEXT NOT NULL,
    immutable_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, repair_action_id, report_version)
);
CREATE TABLE IF NOT EXISTS d3_ticket_resolution_entries (
    entry_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    delivery_action_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    content_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, ticket_id, delivery_action_id)
);
CREATE TABLE IF NOT EXISTS d3_delivery_records (
    delivery_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    delivery_action_id TEXT NOT NULL UNIQUE,
    ticket_id TEXT NOT NULL,
    report_ref TEXT NOT NULL,
    report_version INTEGER NOT NULL,
    payload_digest TEXT NOT NULL,
    ticket_entry_id TEXT NOT NULL,
    delivery_receipt_json TEXT NOT NULL,
    committed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d3_local_reports (
    report_ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT,
    outcome TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    immutable_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, outcome)
);
CREATE TABLE IF NOT EXISTS d5_memories (
    memory_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    project_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type = 'EPISODIC'),
    problem_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    applicability_constraints_json TEXT NOT NULL,
    source_task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    source_evidence_ids_json TEXT NOT NULL,
    source_report_ref TEXT,
    source_verification_id TEXT,
    source_outcome TEXT NOT NULL DEFAULT 'REPAIRED_VERIFIED'
        CHECK (source_outcome IN ('REPAIRED_VERIFIED', 'DIAGNOSED', 'SCOPE_ESCALATED')),
    schema_version TEXT NOT NULL DEFAULT 'd5-legacy-v1',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    experience_json TEXT NOT NULL DEFAULT '{}',
    content_digest TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL CHECK (state IN ('CANDIDATE', 'ACTIVE', 'REVOKED')),
    version INTEGER NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    revoked_by TEXT,
    revoked_at TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, problem_type, source_task_id),
    CHECK (
        (source_outcome = 'REPAIRED_VERIFIED'
            AND source_report_ref IS NOT NULL AND source_verification_id IS NOT NULL)
        OR
        (source_outcome IN ('DIAGNOSED', 'SCOPE_ESCALATED')
            AND source_report_ref IS NULL AND source_verification_id IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_d5_memories_lookup
    ON d5_memories(tenant_id, project_id, problem_type, state, expires_at);
CREATE TABLE IF NOT EXISTS d5_memory_events (
    event_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES d5_memories(memory_id),
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CANDIDATE_CREATED', 'CONFIRMED', 'REVOKED')),
    actor_id TEXT NOT NULL,
    memory_version INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS semantic_memories (
    memory_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    project_id TEXT NOT NULL,
    memory_kind TEXT NOT NULL CHECK (memory_kind IN ('ALIAS', 'INTERFACE_CONVENTION', 'WORK_CONSTRAINT')),
    memory_key TEXT NOT NULL,
    content TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    source_task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    source_refs_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('CANDIDATE', 'ACTIVE', 'REVISED', 'REVOKED', 'EXPIRED')),
    version INTEGER NOT NULL CHECK (version > 0),
    supersedes_memory_id TEXT REFERENCES semantic_memories(memory_id),
    supersedes_version INTEGER,
    created_by TEXT NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    revoked_by TEXT,
    revoked_at TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK ((supersedes_memory_id IS NULL AND supersedes_version IS NULL)
        OR (supersedes_memory_id IS NOT NULL AND supersedes_version IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_semantic_memory_active_key
    ON semantic_memories(tenant_id, project_id, memory_kind, memory_key)
    WHERE state = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_semantic_memory_scope
    ON semantic_memories(tenant_id, project_id, state, expires_at);
CREATE TABLE IF NOT EXISTS semantic_memory_events (
    event_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES semantic_memories(memory_id),
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CANDIDATE_CREATED', 'CONFIRMED', 'REVISED', 'REVOKED', 'EXPIRED')),
    actor_id TEXT NOT NULL,
    memory_version INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_semantic_memory_events_scope
    ON semantic_memory_events(memory_id, memory_version, occurred_at);
CREATE TABLE IF NOT EXISTS semantic_memory_commands (
    command_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    command_kind TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, actor_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS semantic_memory_project_approvers (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id)
);
CREATE TABLE IF NOT EXISTS d5_context_provenance (
    call_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    attempt_id TEXT NOT NULL UNIQUE REFERENCES d2_attempts(attempt_id),
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    tool_schema_version TEXT NOT NULL,
    tool_schema_digest TEXT NOT NULL,
    selected_skill_name TEXT,
    selected_skill_version TEXT,
    selected_skill_digest TEXT,
    selected_memories_json TEXT NOT NULL,
    selected_knowledge_json TEXT NOT NULL DEFAULT '[]',
    evidence_ids_json TEXT NOT NULL,
    selected_input_messages_json TEXT NOT NULL DEFAULT '[]',
    task_run_control_json TEXT NOT NULL DEFAULT '{}',
    context_budget_json TEXT NOT NULL DEFAULT '{}',
    context_blocks_json TEXT NOT NULL DEFAULT '[]',
    summary_refs_json TEXT NOT NULL DEFAULT '[]',
    excluded_sources_json TEXT NOT NULL DEFAULT '[]',
    built_at TEXT NOT NULL,
    model_status TEXT NOT NULL DEFAULT 'PREPARED',
    completed_at TEXT,
    error_class TEXT
);
CREATE INDEX IF NOT EXISTS ix_d5_context_task ON d5_context_provenance(task_id, built_at);
CREATE TABLE IF NOT EXISTS chat_attempts (
    attempt_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES task_bindings(task_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    model_id TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED', 'STREAMING', 'SUCCEEDED', 'FAILED', 'INTERRUPTED')),
    provider_response_id TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    error_class TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (run_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS ix_chat_attempts_run ON chat_attempts(run_id, attempt_no);
CREATE TABLE IF NOT EXISTS chat_context_manifests (
    manifest_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES chat_attempts(attempt_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    task_id TEXT,
    selected_message_ids_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    memory_refs_json TEXT NOT NULL,
    model_call_refs_json TEXT NOT NULL,
    excluded_sources_json TEXT NOT NULL,
    truncation_json TEXT NOT NULL,
    trusted_state_digest TEXT,
    prompt_digest TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chat_context_run ON chat_context_manifests(run_id, created_at);
CREATE TABLE IF NOT EXISTS context_compression_attempts (
    attempt_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES task_bindings(task_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    model_id TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED', 'SUCCEEDED', 'FAILED', 'INVALIDATED', 'INTERRUPTED')),
    source_dependencies_json TEXT NOT NULL,
    estimated_input_tokens INTEGER NOT NULL CHECK (estimated_input_tokens >= 0),
    provider_response_id TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    summary_id TEXT,
    error_class TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (run_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS ix_context_compression_run
    ON context_compression_attempts(run_id, attempt_no);
CREATE TABLE IF NOT EXISTS context_summaries (
    summary_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES task_bindings(task_id) ON DELETE CASCADE,
    summary_version INTEGER NOT NULL CHECK (summary_version > 0),
    state TEXT NOT NULL CHECK (state IN ('CURRENT', 'SUPERSEDED', 'INVALID')),
    strategy TEXT NOT NULL CHECK (strategy IN ('ROLLING_SUMMARY', 'HYBRID')),
    summary_json TEXT NOT NULL,
    summary_digest TEXT NOT NULL,
    covered_from_seq INTEGER NOT NULL,
    covered_to_seq INTEGER NOT NULL,
    depends_on_summary_id TEXT REFERENCES context_summaries(summary_id),
    source_attempt_id TEXT NOT NULL REFERENCES context_compression_attempts(attempt_id),
    model_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    invalidation_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_context_summaries_scope
    ON context_summaries(tenant_id, session_id, task_id, state, summary_version);
CREATE TABLE IF NOT EXISTS context_summary_dependencies (
    summary_id TEXT NOT NULL REFERENCES context_summaries(summary_id) ON DELETE CASCADE,
    dependency_kind TEXT NOT NULL CHECK (dependency_kind IN ('MESSAGE', 'ASSISTANT_MESSAGE', 'MODEL_ATTEMPT', 'MEMORY', 'EVIDENCE', 'TASK_STATE', 'KNOWLEDGE', 'SKILL', 'SUMMARY')),
    dependency_ref TEXT NOT NULL,
    dependency_version TEXT,
    dependency_digest TEXT NOT NULL,
    source_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (summary_id, dependency_kind, dependency_ref)
);
CREATE INDEX IF NOT EXISTS ix_context_summary_dependency_ref
    ON context_summary_dependencies(dependency_kind, dependency_ref);
CREATE TABLE IF NOT EXISTS chat_message_summary_sources (
    message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    summary_id TEXT NOT NULL REFERENCES context_summaries(summary_id),
    summary_version INTEGER NOT NULL,
    summary_digest TEXT NOT NULL,
    PRIMARY KEY (message_id, summary_id)
);
CREATE TABLE IF NOT EXISTS chat_answer_chunks (
    chunk_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES chat_attempts(attempt_id) ON DELETE CASCADE,
    chunk_seq INTEGER NOT NULL CHECK (chunk_seq > 0),
    body TEXT NOT NULL,
    body_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (attempt_id, chunk_seq)
);
CREATE TABLE IF NOT EXISTS chat_message_sources (
    message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('MESSAGE', 'EVIDENCE', 'MEMORY', 'TASK_STATE', 'MODEL_ATTEMPT')),
    source_ref TEXT NOT NULL,
    source_version TEXT,
    source_digest TEXT NOT NULL,
    PRIMARY KEY (message_id, source_kind, source_ref)
);
CREATE INDEX IF NOT EXISTS ix_chat_message_sources_ref ON chat_message_sources(source_kind, source_ref);
CREATE TABLE IF NOT EXISTS chat_run_answers (
    run_id TEXT PRIMARY KEY REFERENCES task_runs(run_id) ON DELETE CASCADE,
    message_id TEXT NOT NULL UNIQUE REFERENCES messages(message_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES chat_attempts(attempt_id),
    manifest_id TEXT NOT NULL REFERENCES chat_context_manifests(manifest_id),
    body_digest TEXT NOT NULL,
    committed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS investigation_update_assessments (
    assessment_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id) ON DELETE CASCADE,
    source_message_id TEXT NOT NULL UNIQUE REFERENCES messages(message_id) ON DELETE CASCADE,
    source_digest TEXT NOT NULL,
    conversation_digest TEXT NOT NULL,
    expected_control_revision INTEGER NOT NULL CHECK (expected_control_revision >= 0),
    prior_input_text TEXT NOT NULL,
    intent TEXT CHECK (intent IS NULL OR intent IN ('FOLLOW_UP', 'CRITICAL_CORRECTION', 'HYPOTHESIS', 'OUT_OF_SCOPE')),
    change_summary TEXT,
    status TEXT NOT NULL CHECK (status IN ('ASSESSING', 'NO_UPDATE', 'PENDING_CONFIRMATION', 'CONFIRMED', 'CANCELLED', 'STALE', 'FAILED')),
    operation_id TEXT NOT NULL UNIQUE,
    correction_message_id TEXT REFERENCES messages(message_id),
    investigation_run_id TEXT REFERENCES task_runs(run_id),
    failure_code TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    confirmed_at TEXT,
    cancelled_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_investigation_update_task
    ON investigation_update_assessments(tenant_id, task_id, created_at);
CREATE TABLE IF NOT EXISTS investigation_update_attempts (
    attempt_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL REFERENCES investigation_update_assessments(assessment_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    model_id TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED', 'SUCCEEDED', 'FAILED')),
    response_digest TEXT,
    provider_response_id TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    error_code TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (assessment_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS ix_investigation_update_attempts
    ON investigation_update_attempts(assessment_id, attempt_no);
CREATE TABLE IF NOT EXISTS worker_retry_state (
    run_id TEXT PRIMARY KEY REFERENCES task_runs(run_id) ON DELETE CASCADE,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 3 CHECK (max_retries BETWEEN 0 AND 10),
    next_attempt_at TEXT,
    last_error_code TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_worker_retry_due ON worker_retry_state(next_attempt_at, retry_count);
"""


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    db_path = Path(path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(path: str | Path) -> None:
    with connect(path) as connection:
        # executescript normally commits any open transaction before executing.
        # Put the transaction opener inside the script so schema creation and the
        # versioned compatibility backfill commit or roll back together.
        from opspilot.domain.s3 import SCHEMA as S3_SCHEMA
        connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + S3_SCHEMA)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > 13:
            raise RuntimeError(f"Unsupported Domain schema version: {version}.")
        if version < 1:
            # A pre-vNext Task is safe to initialize at revision 0 only when the new
            # admission tables contain no history that could represent pending input.
            for task in connection.execute("SELECT task_id, tenant_id, actor_id FROM task_bindings").fetchall():
                task_id = str(task["task_id"])
                tenant_id = str(task["tenant_id"])
                new_history = connection.execute(
                    "SELECT 1 FROM messages WHERE task_id = ? UNION ALL SELECT 1 FROM task_runs WHERE task_id = ? LIMIT 1",
                    (task_id, task_id),
                ).fetchone()
                if new_history is not None:
                    continue
                connection.execute(
                    """INSERT OR IGNORE INTO task_controls
                       (task_id, tenant_id, terminal_state, control_revision,
                        pending_critical_message_seq, applied_critical_message_seq,
                        changed_at, changed_by, reason)
                       VALUES (?, ?, 'ACTIVE', 0, NULL, 0, CURRENT_TIMESTAMP, ?, 'legacy_revision_0_migration')""",
                    (task_id, tenant_id, str(task["actor_id"])),
                )
                session_id = f"session-legacy-{task_id}"
                connection.execute(
                    """INSERT OR IGNORE INTO sessions (session_id, tenant_id, owner_id, created_at, updated_at)
                       VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    (session_id, tenant_id, str(task["actor_id"])),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO session_task_links
                       (session_id, task_id, tenant_id, linked_at, is_primary)
                       VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)""",
                    (session_id, task_id, tenant_id),
                )
            connection.execute(
                """INSERT OR IGNORE INTO d3_plan_control_bindings
                   (tenant_id, task_id, plan_hash, bound_control_revision, consumed_message_seq,
                    task_run_id, bound_at)
                   SELECT p.tenant_id, p.task_id, p.plan_hash, 0, 0, NULL, p.created_at
                   FROM d3_plans AS p JOIN task_controls AS c
                     ON c.task_id = p.task_id AND c.tenant_id = p.tenant_id
                   WHERE c.control_revision = 0 AND c.pending_critical_message_seq IS NULL"""
            )
            connection.execute("PRAGMA user_version = 1")
            version = 1
        if version < 2:
            connection.execute("PRAGMA user_version = 2")
            version = 2
        if version < 3:
            connection.execute(
                """INSERT OR IGNORE INTO worker_retry_state (run_id, retry_count, max_retries, next_attempt_at, updated_at)
                   SELECT run_id, 0, 3, NULL, created_at FROM task_runs
                   WHERE status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')"""
            )
            connection.execute("PRAGMA user_version = 3")
            version = 3
        if version < 4:
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(d5_context_provenance)").fetchall()
            }
            if "selected_input_messages_json" not in columns:
                connection.execute(
                    "ALTER TABLE d5_context_provenance ADD COLUMN selected_input_messages_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "task_run_control_json" not in columns:
                connection.execute(
                    "ALTER TABLE d5_context_provenance ADD COLUMN task_run_control_json TEXT NOT NULL DEFAULT '{}'"
                )
            connection.execute("PRAGMA user_version = 4")
            version = 4
        if version < 5:
            connection.execute("PRAGMA user_version = 5")
            version = 5
        if version < 6:
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(auth_events)").fetchall()
            }
            if "request_id" not in columns:
                connection.execute("ALTER TABLE auth_events ADD COLUMN request_id TEXT")
            if "credential_policy_version" not in columns:
                connection.execute("ALTER TABLE auth_events ADD COLUMN credential_policy_version INTEGER")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_events_request_id "
                "ON auth_events(request_id) WHERE request_id IS NOT NULL"
            )
            connection.execute("PRAGMA user_version = 6")
            version = 6
        if version < 7:
            attempt_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(d2_attempts)").fetchall()
            }
            if "run_id" not in attempt_columns:
                connection.execute("ALTER TABLE d2_attempts ADD COLUMN run_id TEXT")
            provenance_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(d5_context_provenance)").fetchall()
            }
            if "selected_knowledge_json" not in provenance_columns:
                connection.execute(
                    "ALTER TABLE d5_context_provenance ADD COLUMN selected_knowledge_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.execute("PRAGMA user_version = 7")
            version = 7
        if version < 8:
            connection.execute("PRAGMA user_version = 8")
            version = 8
        if version < 9:
            memory_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(d5_memories)").fetchall()
            }
            required_v9 = {
                "source_outcome", "schema_version", "source_refs_json",
                "experience_json", "content_digest",
            }
            if not required_v9.issubset(memory_columns):
                # Rebuild only the D5 parent and event tables. Renaming the parent
                # updates the old event FK, so the v8 history can be copied before
                # the old child and parent are dropped in that order.
                connection.execute("ALTER TABLE d5_memories RENAME TO d5_memories_v8")
                connection.execute("ALTER TABLE d5_memory_events RENAME TO d5_memory_events_v8")
                connection.execute("DROP INDEX IF EXISTS ix_d5_memories_lookup")
                connection.execute(
                    """CREATE TABLE d5_memories (
                        memory_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                        project_id TEXT NOT NULL,
                        type TEXT NOT NULL CHECK (type = 'EPISODIC'),
                        problem_type TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        applicability_constraints_json TEXT NOT NULL,
                        source_task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
                        source_evidence_ids_json TEXT NOT NULL,
                        source_report_ref TEXT,
                        source_verification_id TEXT,
                        source_outcome TEXT NOT NULL
                            CHECK (source_outcome IN ('REPAIRED_VERIFIED', 'DIAGNOSED', 'SCOPE_ESCALATED')),
                        schema_version TEXT NOT NULL,
                        source_refs_json TEXT NOT NULL,
                        experience_json TEXT NOT NULL,
                        content_digest TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ('CANDIDATE', 'ACTIVE', 'REVOKED')),
                        version INTEGER NOT NULL,
                        confirmed_by TEXT,
                        confirmed_at TEXT,
                        revoked_by TEXT,
                        revoked_at TEXT,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE (tenant_id, project_id, problem_type, source_task_id),
                        CHECK (
                            (source_outcome = 'REPAIRED_VERIFIED'
                                AND source_report_ref IS NOT NULL AND source_verification_id IS NOT NULL)
                            OR
                            (source_outcome IN ('DIAGNOSED', 'SCOPE_ESCALATED')
                                AND source_report_ref IS NULL AND source_verification_id IS NULL)
                        )
                    )"""
                )
                connection.execute(
                    """CREATE TABLE d5_memory_events (
                        event_id TEXT PRIMARY KEY,
                        memory_id TEXT NOT NULL REFERENCES d5_memories(memory_id),
                        tenant_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK (event_type IN ('CANDIDATE_CREATED', 'CONFIRMED', 'REVOKED')),
                        actor_id TEXT NOT NULL,
                        memory_version INTEGER NOT NULL,
                        occurred_at TEXT NOT NULL,
                        details_json TEXT NOT NULL
                    )"""
                )
                old_rows = connection.execute("SELECT * FROM d5_memories_v8").fetchall()
                for old in old_rows:
                    try:
                        evidence_ids = json.loads(str(old["source_evidence_ids_json"]))
                    except (json.JSONDecodeError, TypeError):
                        evidence_ids = []
                    source_refs: list[dict[str, object]] = []
                    report = connection.execute(
                        "SELECT content_digest, repair_action_id FROM d3_report_artifacts WHERE report_ref = ?",
                        (old["source_report_ref"],),
                    ).fetchone()
                    ledger = connection.execute(
                        "SELECT ledger_id, result_digest FROM d3_action_ledgers "
                        "WHERE task_id = ? AND action_id = ? AND action_kind = 'REPAIR' "
                        "AND status = 'COMMITTED'",
                        (old["source_task_id"], report["repair_action_id"] if report is not None else ""),
                    ).fetchone()
                    if ledger is not None:
                        source_refs.append({
                            "kind": "REPAIR_LEDGER", "id": str(ledger["ledger_id"]),
                            "digest_or_version": str(ledger["result_digest"]),
                        })
                    verification = connection.execute(
                        "SELECT result_digest FROM d3_verification_receipts WHERE verification_id = ?",
                        (old["source_verification_id"],),
                    ).fetchone()
                    if report is not None:
                        source_refs.append({
                            "kind": "FROZEN_REPORT", "id": str(old["source_report_ref"]),
                            "digest_or_version": str(report["content_digest"]),
                        })
                    if verification is not None:
                        source_refs.append({
                            "kind": "VERIFICATION_RECEIPT", "id": str(old["source_verification_id"]),
                            "digest_or_version": str(verification["result_digest"]),
                        })
                    for evidence_id in evidence_ids if isinstance(evidence_ids, list) else []:
                        evidence = connection.execute(
                            "SELECT digest FROM d2_evidence WHERE evidence_id = ? AND task_id = ?",
                            (str(evidence_id), str(old["source_task_id"])),
                        ).fetchone()
                        if evidence is not None:
                            source_refs.append({
                                "kind": "EVIDENCE", "id": str(evidence_id),
                                "digest_or_version": str(evidence["digest"]),
                            })
                    source_refs.sort(key=lambda item: (str(item["kind"]), str(item["id"])))
                    experience = {
                        "schema_version": "d5-legacy-v1",
                        "symptom_pattern": "Legacy D5 method hint; no case-specific extraction was performed.",
                        "case_specific_facts": [],
                        "investigation_guidance": str(old["summary"]),
                        "applicability": str(old["applicability_constraints_json"]),
                        "limitations": ["Legacy fixed guidance is not case-specific learning."],
                        "legacy_fixed_guidance": True,
                    }
                    payload = {
                        "schema_version": "d5-legacy-v1",
                        "problem_type": str(old["problem_type"]),
                        "source_outcome": "REPAIRED_VERIFIED",
                        "summary": str(old["summary"]),
                        "source_refs": source_refs,
                        "experience": experience,
                    }
                    content_digest = hashlib.sha256(json.dumps(
                        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                    ).encode("utf-8")).hexdigest()
                    connection.execute(
                        """INSERT INTO d5_memories
                           (memory_id, tenant_id, project_id, type, problem_type, summary,
                            applicability_constraints_json, source_task_id, source_evidence_ids_json,
                            source_report_ref, source_verification_id, source_outcome, schema_version,
                            source_refs_json, experience_json, content_digest, state, version,
                            confirmed_by, confirmed_at, revoked_by, revoked_at, expires_at, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'REPAIRED_VERIFIED', 'd5-legacy-v1',
                                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            old["memory_id"], old["tenant_id"], old["project_id"], old["type"],
                            old["problem_type"], old["summary"], old["applicability_constraints_json"],
                            old["source_task_id"], old["source_evidence_ids_json"],
                            old["source_report_ref"], old["source_verification_id"],
                            json.dumps(source_refs, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            json.dumps(experience, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            content_digest, old["state"], old["version"], old["confirmed_by"],
                            old["confirmed_at"], old["revoked_by"], old["revoked_at"],
                            old["expires_at"], old["created_at"],
                        ),
                    )
                connection.execute(
                    """INSERT INTO d5_memory_events
                       (event_id, memory_id, tenant_id, project_id, event_type, actor_id,
                        memory_version, occurred_at, details_json)
                       SELECT event_id, memory_id, tenant_id, project_id, event_type, actor_id,
                              memory_version, occurred_at, details_json
                       FROM d5_memory_events_v8"""
                )
                connection.execute("DROP TABLE d5_memory_events_v8")
                connection.execute("DROP TABLE d5_memories_v8")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS ix_d5_memories_lookup "
                    "ON d5_memories(tenant_id, project_id, problem_type, state, expires_at)"
                )
            connection.execute("PRAGMA user_version = 9")
            version = 9
        if version < 10:
            provenance_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(d5_context_provenance)").fetchall()
            }
            for name, definition in (
                ("context_budget_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("context_blocks_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("summary_refs_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("excluded_sources_json", "TEXT NOT NULL DEFAULT '[]'"),
            ):
                if name not in provenance_columns:
                    connection.execute(f"ALTER TABLE d5_context_provenance ADD COLUMN {name} {definition}")
            connection.execute("PRAGMA user_version = 10")
            version = 10
        if version < 11:
            connection.execute(
                """INSERT OR IGNORE INTO semantic_memory_project_approvers
                   (tenant_id, project_id, actor_id, active, granted_by, granted_at)
                   SELECT DISTINCT o.tenant_id, 'service:' || b.service_id, o.actor_id, 1,
                          'migration:v11_same_tenant_approver', CURRENT_TIMESTAMP
                   FROM trusted_operators AS o JOIN task_bindings AS b
                     ON b.tenant_id = o.tenant_id
                   WHERE o.role = 'APPROVER'"""
            )
            connection.execute("PRAGMA user_version = 11")
            version = 11
        if version < 12:
            connection.execute("PRAGMA user_version = 12")
        if version < 13:
            connection.execute("PRAGMA user_version = 13")


def reset_fixture(path: str | Path, scenario: Scenario) -> None:
    """Reset local demo state. This function is never exposed as an Agent tool."""
    initialize(path)
    status_a = "DISABLED" if scenario == "S1_DISABLED" else "ENABLED"
    s2_scenario = scenario.startswith("S2_")
    with connect(path) as connection:
        connection.execute("DROP TRIGGER IF EXISTS trg_s2_handoff_receipt_no_update")
        connection.execute("DROP TRIGGER IF EXISTS trg_s2_handoff_receipt_no_delete")
        connection.execute("DROP TRIGGER IF EXISTS s3_diagnoses_no_delete")
        for table in (
            "s3_model_contexts",
            "s3_diagnoses",
            "s3_http_observations",
            "s3_receivers",
            "s3_deliveries",
            "s3_orders",
            "investigation_update_attempts",
            "investigation_update_assessments",
            "chat_message_summary_sources",
            "context_summary_dependencies",
            "context_summaries",
            "context_compression_attempts",
            "chat_run_answers",
            "chat_message_sources",
            "chat_answer_chunks",
            "chat_context_manifests",
            "chat_attempts",
            "worker_retry_state",
            "task_run_inputs",
            "task_execution_budgets",
            "session_events",
            "web_auth_sessions",
            "web_worker_state",
            "domain_outbox",
            "approval_resume_links",
            "d3_plan_control_bindings",
            "s2_handoff_receipts",
            "s2_handoff_queue_entries",
            "s2_handoff_drafts",
            "s2_diagnosis_receipts",
            "s2_gate_traces",
            "task_runs",
            "messages",
            "commands",
            "session_task_links",
            "sessions",
            "task_controls",
            "d5_context_provenance",
            "d5_memory_events",
            "d5_memories",
            "semantic_memory_commands",
            "semantic_memory_events",
            "semantic_memories",
            "semantic_memory_project_approvers",
            "d3_local_reports",
            "d3_delivery_records",
            "d3_ticket_resolution_entries",
            "d3_report_artifacts",
            "d3_verification_receipts",
            "d3_action_ledgers",
            "d3_action_intents",
            "d3_action_permissions",
            "d3_approvals",
            "d3_plan_authorization_history",
            "d3_plan_authorizations",
            "d3_plans",
            "tickets",
            "executor_services",
            "d2_tool_faults",
            "d2_reports",
            "d2_evidence",
            "d2_tool_observations",
            "d2_pending_tool_calls",
            "d2_model_traces",
            "d2_attempts",
            "task_bindings",
            "authz_events",
            "auth_events",
            "principal_scope_grants",
            "route_scope_policies",
            "auth_policies",
            "services",
            "integrations",
            "principals",
            "credentials",
            "orders",
            "thread_owners",
            "trusted_operators",
            "tenants",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.executemany(
            "INSERT INTO tenants (tenant_id) VALUES (?)",
            [("tenant-a",), ("tenant-b",)],
        )
        connection.executemany(
            "INSERT INTO trusted_operators (actor_id, tenant_id, role) VALUES (?, ?, ?)",
            [
                ("support-a", "tenant-a", "SUPPORT"),
                ("approver-a", "tenant-a", "APPROVER"),
                ("support-b", "tenant-b", "SUPPORT"),
                ("approver-b", "tenant-b", "APPROVER"),
            ],
        )
        connection.executemany(
            "INSERT INTO executor_services (executor_id, tenant_id, active) VALUES (?, ?, 1)",
            [("executor-a", "tenant-a"), ("executor-b", "tenant-b")],
        )
        connection.executemany(
            "INSERT INTO tickets (tenant_id, ticket_id, status) VALUES (?, ?, 'OPEN')",
            [("tenant-a", "INC-A-001"), ("tenant-b", "INC-B-001")],
        )
        for tenant_id, suffix, principal_status in (
            ("tenant-a", "a", status_a),
            ("tenant-b", "b", "ENABLED"),
        ):
            connection.executemany(
                "INSERT INTO credentials VALUES (?, ?, ?, ?)",
                [
                    (tenant_id, "cred-v1", f"fixture-{suffix}-old-secret", 1),
                    (tenant_id, "cred-v2", f"fixture-{suffix}-current-secret", 2),
                ],
            )
            connection.execute(
                "INSERT INTO principals VALUES (?, ?, ?, ?)",
                (tenant_id, f"principal-{suffix}", principal_status, 2),
            )
            active_credential_ref = "cred-v2" if s2_scenario else "cred-v1"
            config_version = 8 if s2_scenario else 7
            connection.execute(
                "INSERT INTO integrations VALUES (?, ?, ?, ?, ?)",
                (tenant_id, f"integration-{suffix}", f"principal-{suffix}", active_credential_ref, config_version),
            )
            connection.execute(
                "INSERT INTO services VALUES (?, ?, ?, ?)",
                (tenant_id, "orders-demo", f"integration-{suffix}", "/api/orders/demo-order"),
            )
            connection.execute(
                """INSERT INTO semantic_memory_project_approvers
                   (tenant_id, project_id, actor_id, active, granted_by, granted_at)
                   VALUES (?, 'service:orders-demo', ?, 1, 'fixture:trusted-demo-roles', CURRENT_TIMESTAMP)""",
                (tenant_id, f"approver-{suffix}"),
            )
            connection.execute(
                "INSERT INTO auth_policies VALUES (?, ?, ?, ?)",
                (tenant_id, "orders-demo", "cred-v2", 3),
            )
            granted_scopes = [] if (
                tenant_id == "tenant-a" and scenario == "S2_SCOPE_DENIED"
            ) else ["orders.read"]
            connection.execute(
                "INSERT INTO principal_scope_grants "
                "(tenant_id, principal_id, granted_scopes_json, grant_version) VALUES (?, ?, ?, 1)",
                (tenant_id, f"principal-{suffix}", json.dumps(granted_scopes, separators=(",", ":"))),
            )
            connection.execute(
                "INSERT INTO route_scope_policies "
                "(tenant_id, service_id, route, required_scopes_json, scope_policy_version) "
                "VALUES (?, ?, ?, ?, 1)",
                (tenant_id, "orders-demo", "/api/orders/demo-order", '["orders.read"]'),
            )
            connection.execute(
                "INSERT INTO orders VALUES (?, ?, ?)",
                (tenant_id, "demo-order", "CONFIRMED"),
            )
    initialize(path)


def get_service_info(path: str | Path, tenant_id: str, service_id: str) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT s.service_id, s.route, s.tenant_id, s.integration_id,
                   i.credential_ref, i.config_version, i.principal_id,
                   p.status AS principal_status, p.principal_version,
                   a.accepted_credential_ref, a.policy_version
            FROM services AS s
            JOIN integrations AS i
              ON i.tenant_id = s.tenant_id AND i.integration_id = s.integration_id
            JOIN principals AS p
              ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
            JOIN auth_policies AS a
              ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
            WHERE s.tenant_id = ? AND s.service_id = ?
            """,
            (tenant_id, service_id),
        ).fetchone()
    if row is None:
        raise LookupError("Service is not available in the trusted tenant scope.")
    return dict(row)


def get_integration_info(
    path: str | Path, tenant_id: str, integration_id: str
) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT i.integration_id, i.principal_id, i.credential_ref,
                   i.config_version, p.status AS principal_status,
                   p.principal_version
            FROM integrations AS i
            JOIN principals AS p
              ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
            WHERE i.tenant_id = ? AND i.integration_id = ?
            """,
            (tenant_id, integration_id),
        ).fetchone()
    if row is None:
        raise LookupError("Integration is not available in the trusted tenant scope.")
    return dict(row)


def get_credential_secret(path: str | Path, tenant_id: str, credential_ref: str) -> str:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT secret_value FROM credentials WHERE tenant_id = ? AND credential_ref = ?",
            (tenant_id, credential_ref),
        ).fetchone()
    if row is None:
        raise LookupError("Credential reference is not available in the trusted tenant scope.")
    return str(row["secret_value"])


def record_auth_event(
    path: str | Path,
    tenant_id: str,
    integration_id: str,
    principal_id: str,
    service_id: str,
    route: str,
    result_code: str,
    request_id: str | None = None,
    credential_policy_version: int | None = None,
) -> int:
    with connect(path) as connection:
        cursor = connection.execute(
            """INSERT INTO auth_events
               (tenant_id, integration_id, principal_id, service_id, route, result_code,
                request_id, credential_policy_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, integration_id, principal_id, service_id, route, result_code,
             request_id, credential_policy_version),
        )
        return int(cursor.lastrowid)


def authorize_business_request(
    path: str | Path,
    *,
    tenant_id: str,
    service_id: str,
    route: str,
    integration_id: str,
    authorization: str,
    request_id: str,
) -> dict[str, object]:
    """Persist one server-side Authn result and, only after success, its Authz decision."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        service = connection.execute(
            """SELECT s.route, s.integration_id, i.principal_id, p.status AS principal_status,
                      a.accepted_credential_ref, a.policy_version AS credential_policy_version,
                      c.secret_value
               FROM services AS s
               JOIN integrations AS i
                 ON i.tenant_id = s.tenant_id AND i.integration_id = s.integration_id
               JOIN principals AS p
                 ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
               JOIN auth_policies AS a
                 ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
               JOIN credentials AS c
                 ON c.tenant_id = a.tenant_id AND c.credential_ref = a.accepted_credential_ref
               WHERE s.tenant_id = ? AND s.service_id = ?""",
            (tenant_id, service_id),
        ).fetchone()
        if service is None or str(service["route"]) != route:
            return {"http_status": 401, "request_id": request_id}
        if integration_id != str(service["integration_id"]):
            return {"http_status": 401, "request_id": request_id}

        supplied_secret = authorization.removeprefix("Bearer ")
        authenticated = (
            authorization.startswith("Bearer ")
            and hmac.compare_digest(supplied_secret, str(service["secret_value"]))
            and service["principal_status"] == "ENABLED"
        )
        authn_result = "AUTH_ACCEPTED" if authenticated else "AUTH_REJECTED"
        authn = connection.execute(
            """INSERT INTO auth_events
               (request_id, tenant_id, integration_id, principal_id, service_id, route,
                result_code, credential_policy_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (request_id, tenant_id, integration_id, str(service["principal_id"]), service_id,
             route, authn_result, int(service["credential_policy_version"])),
        )
        authn_event_id = int(authn.lastrowid)
        if not authenticated:
            return {
                "http_status": 401,
                "request_id": request_id,
                "authn_event_id": authn_event_id,
            }

        grant = connection.execute(
            """SELECT granted_scopes_json, grant_version FROM principal_scope_grants
               WHERE tenant_id = ? AND principal_id = ?""",
            (tenant_id, str(service["principal_id"])),
        ).fetchone()
        policy = connection.execute(
            """SELECT required_scopes_json, scope_policy_version FROM route_scope_policies
               WHERE tenant_id = ? AND service_id = ? AND route = ?""",
            (tenant_id, service_id, route),
        ).fetchone()
        if grant is None or policy is None:
            # Missing trusted authorization configuration fails closed and is not
            # misrepresented as a known missing-scope root cause.
            required_scopes: list[str] = []
            granted_scopes: list[str] = []
            missing_scopes: list[str] = []
            scope_policy_version = int(policy["scope_policy_version"]) if policy else 0
            grant_version = int(grant["grant_version"]) if grant else 0
            outcome = "DENY"
            reason_code = "AUTHZ_POLICY_UNAVAILABLE"
        else:
            required_scopes = sorted(set(json.loads(str(policy["required_scopes_json"]))))
            granted_scopes = sorted(set(json.loads(str(grant["granted_scopes_json"]))))
            missing_scopes = sorted(set(required_scopes) - set(granted_scopes))
            scope_policy_version = int(policy["scope_policy_version"])
            grant_version = int(grant["grant_version"])
            outcome = "DENY" if missing_scopes else "ALLOW"
            reason_code = "SCOPE_INSUFFICIENT" if missing_scopes else "SCOPE_GRANTED"
        decision = connection.execute(
            """INSERT INTO authz_events
               (request_id, authn_event_id, tenant_id, principal_id, service_id, integration_id,
                route, outcome, reason_code, credential_policy_version, scope_policy_version,
                grant_version, required_scopes_json, granted_scopes_json, missing_scopes_json,
                resource_binding_valid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (request_id, authn_event_id, tenant_id, str(service["principal_id"]), service_id,
             integration_id, route, outcome, reason_code,
             int(service["credential_policy_version"]), scope_policy_version, grant_version,
             json.dumps(required_scopes, separators=(",", ":")),
             json.dumps(granted_scopes, separators=(",", ":")),
             json.dumps(missing_scopes, separators=(",", ":"))),
        )
        return {
            "http_status": 403 if outcome == "DENY" else 200,
            "request_id": request_id,
            "authn_event_id": authn_event_id,
            "authz_event_id": int(decision.lastrowid),
            "outcome": outcome,
            "reason_code": reason_code,
        }


def get_auth_event(path: str | Path, tenant_id: str, event_id: int) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT event_id, tenant_id, integration_id, principal_id,
                      service_id, route, result_code, request_id,
                      credential_policy_version, observed_at
               FROM auth_events WHERE tenant_id = ? AND event_id = ?""",
            (tenant_id, event_id),
        ).fetchone()
    if row is None:
        raise LookupError("Authentication event is not available within the trusted tenant scope.")
    return dict(row)
