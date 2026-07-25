import { appendMessage, getConversation } from "@/lib/dummy/conversations";
import { pickAnswer } from "@/lib/dummy/answer";

// Fake token-by-token stream over Server-Sent Events. The event shapes
// ("delta" / "sources" / "done" / "error") intentionally mirror the
// ChatStreamEvent union in lib/providers/types.ts (plus a "sources" event,
// since real citations come from lib/retrieval.ts rather than the provider
// stream) — swapping this route body for a real provider adapter call later
// shouldn't require touching the client.

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sseLine(event: Record<string, unknown>) {
  return `data: ${JSON.stringify(event)}\n\n`;
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const conversationId = typeof body?.conversationId === "string" ? body.conversationId : "";
  const message = typeof body?.message === "string" ? body.message.trim() : "";

  if (!conversationId || !message) {
    return new Response("conversationId and message are required", { status: 400 });
  }

  const conversation = getConversation(conversationId);
  if (!conversation) {
    return new Response("Conversation not found", { status: 404 });
  }

  const now = () => new Date().toISOString();
  appendMessage(conversationId, {
    id: `msg-${Date.now()}-u`,
    role: "user",
    content: message,
    createdAt: now(),
  });

  const answer = pickAnswer(message);
  const words = answer.text.split(" ");

  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();

      // Simulated "thinking" delay before the first token, mirrors real
      // retrieval + first-token latency.
      await sleep(500);

      let acc = "";
      for (let i = 0; i < words.length; i++) {
        const chunk = (i === 0 ? "" : " ") + words[i];
        acc += chunk;
        controller.enqueue(encoder.encode(sseLine({ type: "delta", text: chunk })));
        await sleep(25 + Math.random() * 45);
      }

      if (answer.sources.length > 0) {
        controller.enqueue(encoder.encode(sseLine({ type: "sources", sources: answer.sources })));
      }

      appendMessage(conversationId, {
        id: `msg-${Date.now()}-a`,
        role: "assistant",
        content: acc,
        createdAt: now(),
        sources: answer.sources.length > 0 ? answer.sources : undefined,
      });

      controller.enqueue(encoder.encode(sseLine({ type: "done" })));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
