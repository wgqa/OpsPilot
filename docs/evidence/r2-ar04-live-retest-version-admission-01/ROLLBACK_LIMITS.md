# Version Rollback Limits

The accepted `chat.py` implementation resolves compact-summary `source_sequences` through the owning compression attempt's scoped source map. The older implementation is pinned in the existing Live Runner and only collects `source_message_ids`; it has not been shown to resolve the new sequence-cited representation.

Therefore a code rollback with already-persisted compact summaries is not verified as safe. Do not reopen or recompact sequence-cited summaries with the old resolver. Preserve raw history and either reconstruct summaries from that raw history or design and independently validate a compatible migration/reconstruction before rollback. This task made no database migration and did not change any production database.
