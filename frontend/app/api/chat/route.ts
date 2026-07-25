import { NextResponse } from "next/server";
import {
  backendError,
  backendFetch,
  normalizeSources,
  resolveRunId,
  toConversation,
} from "@/lib/backend";

export const maxDuration = 120;

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const conversationId =
    typeof body?.conversationId === "string" && body.conversationId
      ? body.conversationId
      : null;
  const message = typeof body?.message === "string" ? body.message.trim() : "";
  const modelId = typeof body?.modelId === "string" ? body.modelId : "";

  if (!message) {
    return NextResponse.json({ error: "message is required" }, { status: 400 });
  }

  try {
    const runId = await resolveRunId();
    let history: Array<{
      role: "user" | "assistant";
      content: string;
      sources?: Array<{ title: string; url: string }>;
    }> = [];
    if (conversationId) {
      const historyResponse = await backendFetch(
        `/api/v1/sessions/${encodeURIComponent(conversationId)}`,
      );
      if (!historyResponse.ok) {
        return NextResponse.json(
          { error: await backendError(historyResponse) },
          { status: historyResponse.status },
        );
      }
      const historyPayload = await historyResponse.json();
      const storedMessages: unknown[] = Array.isArray(
        historyPayload?.data?.messages,
      )
        ? historyPayload.data.messages
        : [];
      history = storedMessages
        .slice(-8)
        .filter(
          (
            item: unknown,
          ): item is {
            role: "user" | "assistant";
            content: string;
            sources?: Array<{ title?: string; url?: string }>;
          } =>
            Boolean(
              item &&
                typeof item === "object" &&
                "role" in item &&
                ((item as { role?: unknown }).role === "user" ||
                  (item as { role?: unknown }).role === "assistant") &&
                "content" in item &&
                typeof (item as { content?: unknown }).content === "string",
            ),
        )
        .map((item) => ({
          role: item.role,
          content: item.content,
          ...(Array.isArray(item.sources)
            ? {
                sources: item.sources
                  .filter(
                    (source) =>
                      source &&
                      typeof source.title === "string" &&
                      typeof source.url === "string",
                  )
                  .map((source) => ({
                    title: source.title as string,
                    url: source.url as string,
                  })),
              }
            : {}),
        }));
    }
    const answerResponse = await backendFetch(
      `/api/v1/runs/${encodeURIComponent(runId)}/answer`,
      {
        method: "POST",
        body: JSON.stringify({ query: message, history, model: modelId }),
      },
    );
    if (!answerResponse.ok) {
      return NextResponse.json(
        { error: await backendError(answerResponse) },
        { status: answerResponse.status },
      );
    }

    const answerPayload = await answerResponse.json();
    const answerData = answerPayload?.data;
    const answer =
      typeof answerData?.answer === "string" ? answerData.answer.trim() : "";
    if (!answer) {
      return NextResponse.json(
        { error: "The answer pipeline returned an empty response." },
        { status: 502 },
      );
    }

    const sources = normalizeSources(answerData?.sources);
    const now = new Date().toISOString();
    const messages = [
      {
        role: "user",
        content: message,
        created_at: now,
      },
      {
        role: "assistant",
        content: answer,
        created_at: now,
        ...(sources ? { sources } : {}),
      },
    ];

    const sessionResponse = conversationId
      ? await backendFetch(
          `/api/v1/sessions/${encodeURIComponent(conversationId)}/messages`,
          {
            method: "POST",
            body: JSON.stringify({ messages }),
          },
        )
      : await backendFetch("/api/v1/sessions", {
          method: "POST",
          body: JSON.stringify({
            title: message.slice(0, 60),
            model_id: modelId,
            messages,
          }),
        });
    if (!sessionResponse.ok) {
      return NextResponse.json(
        { error: await backendError(sessionResponse) },
        { status: sessionResponse.status },
      );
    }

    const sessionPayload = await sessionResponse.json();
    return NextResponse.json({
      conversation: toConversation(sessionPayload.data),
      answer: {
        type: answerData.type,
        path: answerData.path,
        router: answerData.router,
      },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "The Flask backend is unavailable.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
