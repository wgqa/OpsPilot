/** A browser operation identity, not an authorization or a new message store. */
export interface OperationStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface AssistantOperation {
  operationId: string;
  requestDigest: string;
}

export interface ControlledInvestigationProposal {
  rationale: string;
  sourceMessageId: string;
}

/** Use only the currently revalidated MCP result for this exact visible question. */
export function controlledInvestigationProposal(
  sources: {
    current: boolean;
    items: Array<{ tool_name: string; status: string; result: Record<string, unknown> | null }>;
  } | null | undefined,
  sourceMessageId: string,
): ControlledInvestigationProposal | null {
  if (!sources?.current || !sourceMessageId) return null;
  const item = sources.items.find((candidate) => candidate.tool_name === 'propose_controlled_auth_investigation');
  const result = item?.result;
  if (
    !item || item.status !== 'OK' || !result || result.success !== true
    || result.proposal_type !== 'CONTROLLED_AUTH_INVESTIGATION'
    || result.authority !== 'MODEL_SUGGESTION_ONLY_UNTRUSTED'
    || result.source_message_id !== sourceMessageId
    || result.task_created !== false || result.authorization_created !== false
    || result.requires_explicit_user_confirmation !== true
    || typeof result.rationale !== 'string' || !result.rationale.trim()
  ) return null;
  return { rationale: result.rationale, sourceMessageId };
}

export async function beginAssistantOperation(
  store: OperationStore, key: string, payload: object,
  newId: () => string = () => crypto.randomUUID(),
): Promise<AssistantOperation> {
  // Persist a digest, not the user's potentially sensitive pasted material.
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const requestDigest = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  const saved = store.getItem(key);
  if (saved) {
    try {
      const previous = JSON.parse(saved) as Partial<AssistantOperation>;
      if (previous.requestDigest === requestDigest && typeof previous.operationId === 'string' && previous.operationId) {
        return { operationId: previous.operationId, requestDigest };
      }
    } catch { /* A malformed local hint never grants authority; create a fresh operation. */ }
  }
  const operation = { operationId: newId(), requestDigest };
  store.setItem(key, JSON.stringify(operation));
  return operation;
}

export function acknowledgeAssistantOperation(store: OperationStore, key: string, operationId: string): void {
  try {
    const current = JSON.parse(store.getItem(key) ?? 'null') as AssistantOperation | null;
    if (current?.operationId === operationId) store.removeItem(key);
  } catch { /* Leave unrelated or malformed entries untouched. */ }
}
