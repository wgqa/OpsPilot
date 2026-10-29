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
