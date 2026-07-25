import type { ChatMessage, ChatSource, Conversation } from "@/lib/chat/types";

const DEFAULT_BACKEND_URL = "http://backend:5000";

interface BackendSource {
  n?: number;
  id?: string;
  chunk_id?: string;
  title?: string;
  url?: string;
}

interface BackendMessage {
  id?: string;
  role?: string;
  content?: string;
  created_at?: string;
  sources?: BackendSource[];
}

interface BackendSession {
  id?: string;
  title?: string;
  model_id?: string;
  created_at?: string;
  updated_at?: string;
  messages?: BackendMessage[];
}

interface BackendRun {
  id?: string;
  semantic_ready?: boolean;
}

export function backendUrl(path: string): string {
  const base = (process.env.BACKEND_API_URL || DEFAULT_BACKEND_URL).replace(/\/+$/, "");
  return `${base}${path}`;
}

export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(backendUrl(path), {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
}

export async function backendError(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  return (
    payload?.error?.message ||
    payload?.message ||
    `Backend request failed with status ${response.status}.`
  );
}

export function toConversation(session: BackendSession): Conversation {
  const fallbackTime = new Date().toISOString();
  return {
    id: String(session.id || ""),
    title: String(session.title || "New chat"),
    modelId: String(session.model_id || ""),
    createdAt: String(session.created_at || fallbackTime),
    updatedAt: String(session.updated_at || session.created_at || fallbackTime),
    messages: (session.messages || [])
      .filter(
        (message): message is BackendMessage & { role: "user" | "assistant" } =>
          message.role === "user" || message.role === "assistant",
      )
      .map(toMessage),
  };
}

export function toMessage(
  message: BackendMessage & { role: "user" | "assistant" },
): ChatMessage {
  return {
    id: String(message.id || crypto.randomUUID()),
    role: message.role,
    content: String(message.content || ""),
    createdAt: String(message.created_at || new Date().toISOString()),
    sources: normalizeSources(message.sources),
  };
}

export function normalizeSources(value: unknown): ChatSource[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const sources = value
    .filter((source): source is BackendSource => Boolean(source && typeof source === "object"))
    .map((source, index) => ({
      id: String(source.id || source.chunk_id || source.n || index + 1),
      title: String(source.title || "Movie source"),
      url: String(source.url || ""),
    }))
    .filter((source) => source.url);
  return sources.length > 0 ? sources : undefined;
}

export async function resolveRunId(): Promise<string> {
  const configured = process.env.BACKEND_RUN_ID?.trim();
  if (configured) return configured;

  const response = await backendFetch("/api/v1/runs");
  if (!response.ok) throw new Error(await backendError(response));
  const payload = await response.json();
  const runs: BackendRun[] = Array.isArray(payload?.data) ? payload.data : [];
  const semanticReady = runs.find((run) => run?.semantic_ready);
  const selected = semanticReady || runs[0];
  if (!selected?.id) {
    throw new Error("No movie data run is available. Complete data ingestion first.");
  }
  return String(selected.id);
}
