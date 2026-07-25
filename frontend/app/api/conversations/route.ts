import { NextResponse } from "next/server";
import {
  backendError,
  backendFetch,
  toConversation,
} from "@/lib/backend";

export async function GET() {
  try {
    const response = await backendFetch("/api/v1/sessions");
    if (!response.ok) {
      return NextResponse.json(
        { error: await backendError(response) },
        { status: response.status },
      );
    }
    const payload = await response.json();
    const sessions = Array.isArray(payload?.data) ? payload.data : [];
    return NextResponse.json({
      conversations: sessions.map(toConversation),
      count: sessions.length,
    });
  } catch (error) {
    return backendUnavailable(error);
  }
}
export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const response = await backendFetch("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: typeof body?.title === "string" ? body.title : "New chat",
        model_id: typeof body?.modelId === "string" ? body.modelId : "",
        messages: Array.isArray(body?.messages) ? body.messages : [],
      }),
    });
    if (!response.ok) {
      return NextResponse.json(
        { error: await backendError(response) },
        { status: response.status },
      );
    }
    const payload = await response.json();
    return NextResponse.json(
      { conversation: toConversation(payload.data) },
      { status: 201 },
    );
  } catch (error) {
    return backendUnavailable(error);
  }
}

function backendUnavailable(error: unknown) {
  const message = error instanceof Error ? error.message : "The Flask backend is unavailable.";
  return NextResponse.json({ error: message }, { status: 502 });
}
