from __future__ import annotations

import hmac
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
    source_report_ref TEXT NOT NULL,
    source_verification_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('CANDIDATE', 'ACTIVE', 'REVOKED')),
    version INTEGER NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    revoked_by TEXT,
    revoked_at TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, problem_type, source_task_id)
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
        connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > 8:
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


def reset_fixture(path: str | Path, scenario: Scenario) -> None:
    """Reset local demo state. This function is never exposed as an Agent tool."""
    initialize(path)
    status_a = "DISABLED" if scenario == "S1_DISABLED" else "ENABLED"
    s2_scenario = scenario.startswith("S2_")
    with connect(path) as connection:
        connection.execute("DROP TRIGGER IF EXISTS trg_s2_handoff_receipt_no_update")
        connection.execute("DROP TRIGGER IF EXISTS trg_s2_handoff_receipt_no_delete")
        for table in (
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
