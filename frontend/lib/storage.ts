import type { Conversation } from "./dummy/conversations";

// Browser-local persistence for chat history, layered on top of the dummy
// server store (frontend/lib/dummy/conversations.ts). The server store stays
// the source of truth for a fresh browser / other clients; this just makes
// a given browser's session survive reloads without a real DB. Drop this
// once conversations are persisted server-side against a real database.

const STORAGE_KEY = "cinebot:chat-state:v1";

export interface StoredChatState {
  conversations: Conversation[];
  activeId: string | null;
  selectedModelId: string;
}

export function loadChatState(): StoredChatState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.conversations)) return null;
    return parsed as StoredChatState;
  } catch {
    return null;
  }
}

export function saveChatState(state: StoredChatState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Private browsing / quota exceeded — history just won't survive a reload this time.
  }
}

export function clearChatState(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
