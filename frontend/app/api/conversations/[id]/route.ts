import { NextResponse } from "next/server";
import {
  backendError,
  backendFetch,
  toConversation,
} from "@/lib/backend";

interface RouteContext {
  params: Promise<{ id: string }>;
}
export async function GET(_request: Request, { params }: RouteContext) {
  return sessionRequest(await params, { method: "GET" });
}

export async function PATCH(request: Request, { params }: RouteContext) {
  const body = await request.json().catch(() => ({}));
  const title = typeof body?.title === "string" ? body.title.trim() : "";
  if (!title) {
    return NextResponse.json({ error: "title is required" }, { status: 400 });
  }
  return sessionRequest(await params, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function DELETE(_request: Request, { params }: RouteContext) {
  const { id } = await params;
  try {
    const response = await backendFetch(`/api/v1/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      return NextResponse.json(
        { error: await backendError(response) },
        { status: response.status },
      );
    }
    return NextResponse.json({ ok: true, id });
  } catch (error) {
    return backendUnavailable(error);
  }
}

async function sessionRequest({ id }: { id: string }, init: RequestInit) {
  try {
    const response = await backendFetch(
      `/api/v1/sessions/${encodeURIComponent(id)}`,
      init,
    );
    if (!response.ok) {
      return NextResponse.json(
        { error: await backendError(response) },
        { status: response.status },
      );
    }
    const payload = await response.json();
    return NextResponse.json({ conversation: toConversation(payload.data) });
  } catch (error) {
    return backendUnavailable(error);
  }
}

function backendUnavailable(error: unknown) {
  const message = error instanceof Error ? error.message : "The Flask backend is unavailable.";
  return NextResponse.json({ error: message }, { status: 502 });
}
