import type { Conversation } from "./dummy/conversations";

// Browser-local persistence for chat history, layered on top of the dummy
// server store (frontend/lib/dummy/conversations.ts). The server store stays
// the source of truth for a fresh browser / other clients; this just makes
// a given browser's session survive reloads without a real DB. Drop this
// once conversations are persisted server-side against a real database.
//
// Scoped per user id — this browser's localStorage can hold multiple local
// accounts (see lib/auth.ts), and each must see only its own chat history.

function storageKey(userId: string): string {
  return `cinebot:chat-state:v1:${userId}`;
}

export interface StoredChatState {
  conversations: Conversation[];
  activeId: string | null;
  selectedModelId: string;
}

export function loadChatState(userId: string): StoredChatState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.conversations)) return null;
    return parsed as StoredChatState;
  } catch {
    return null;
  }
}

export function saveChatState(userId: string, state: StoredChatState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(userId), JSON.stringify(state));
  } catch {
    // Private browsing / quota exceeded — history just won't survive a reload this time.
  }
}

export function clearChatState(userId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(storageKey(userId));
  } catch {
    // ignore
  }
}
