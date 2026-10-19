# API Scope Guide — Current

Document ID: `api-scope-current`
Version: `1.0.0`
Valid from: `2026-01-01`
Source: OpsPilot local API authorization guide

Route requirements are determined by the current trusted route-scope policy. A permission request should identify the fixed service, integration, principal, route, current required scopes, current granted scopes, and the missing-scope difference. Include a real correlated Request ID and the policy/grant versions shown by current Domain evidence.

An HTTP status is a symptom, not a permission decision. An authentication rejection is distinct from an authorization denial. A 403 can support a scope diagnosis only when the current trusted Authz Decision is `DENY / SCOPE_INSUFFICIENT`, its resource binding is valid, its Request ID matches the authenticated event, and `missing_scopes` equals `required_scopes - granted_scopes`.

This document is explanatory only. The current Domain Policy and Grant rows are authoritative. A draft does not submit a request, change authorization, or prove that the service was repaired.
