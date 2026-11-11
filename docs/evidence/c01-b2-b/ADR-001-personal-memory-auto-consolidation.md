# ADR-001: Automatic consolidation for Personal Memory

**Status:** Candidate for independent review
**Scope:** C01-B2-B only

## Decision

When an owner explicitly enables automatic learning, the existing Worker may consolidate a bounded batch of that owner's successful direct `CHAT_READONLY` messages into the existing `personal_memories` store. New records use `AUTO_LEARNED`, remain scoped to the authenticated owner and tenant, expire after the existing 180-day lifetime, and use the existing Personal Memory retrieval path. They never become Business Memory, Semantic Memory, Episodic Memory, evidence, permissions, or instructions with elevated authority.

The first implementation uses one durable `personal_memory_consolidation_jobs` table for per-session progress and recovery. It collects at least six new successful user messages, waits ten minutes after a successful batch, reads at most twelve messages, and accepts at most four proposals. The model quotes one to three direct source messages for each proposal. The program revalidates owner, tenant, session, chat/run status, source digest, quote support, memory version, revocation, expiry, and the current setting inside the write transaction.

New learning defaults off and is separate from recall. Turning recall off also turns learning off. Enabling learning does not create Runtime Grant authority: the extraction request is an additional bounded call on the source chat Run and must use its existing Runtime Grant, dispatch authorization, spend ledger, and response recovery. Unknown provider outcomes are terminal and are never blindly resent. A durable response can be replayed locally if committing the memory fails.

Automatic consolidation may add or deduplicate records. It may revise only an existing `AUTO_LEARNED` record after a direct correction cue. It cannot replace `USER_EXPLICIT` or `USER_CONFIRMED` records, and automatic processing cannot reactivate revoked or expired records. A new explicit save continues to use the existing B2-A path.

## Rationale and limits

This reuses the existing Worker, Runtime Grant, Personal Memory lifecycle, source validation, and retrieval code. It adds no queue service, provider client, approval workflow, memory framework, embedding store, or second store. The prompt excludes quoted and third-party material, while source quotes and current digests provide a program-checked boundary. Prompt compliance and automatic extraction quality remain model behaviors and are not claimed as proven against a paid provider in this offline candidate.

The current personal memory data model supports only owner-scoped records with the existing 180-day expiry and three-item PINNED limit. Consolidation is deliberately simple and bounded; semantic conflict resolution, correction confirmation, global preferences beyond the existing Personal Memory scope, broader sensitive-data classification, and cross-owner/project memory are out of scope.

## Consequences

- The user sees an explicit setting, an extra-model-call/cost explanation, and the `AUTO_LEARNED` source label.
- Batch attempts and outcomes survive Worker restart; a repeated successful preference is deduplicated.
- Runtime Grant remains the only provider spend authority.
- Business and episodic memory approval/source contracts remain unchanged.
- A real-provider evaluation requires a separate explicit authorization after independent offline acceptance.
