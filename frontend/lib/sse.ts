// Minimal client-side parser for the "data: {...}\n\n" SSE framing emitted
// by app/api/chat/route.ts. Pure browser fetch + ReadableStream, no
// EventSource (which can't do POST bodies).
export async function* readSSE(response: Response): AsyncGenerator<Record<string, unknown>> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const dataLine = rawEvent.split("\n").find((l) => l.startsWith("data: "));
      if (dataLine) {
        try {
          yield JSON.parse(dataLine.slice(6));
        } catch {
          // ignore malformed frame
        }
      }
    }
  }
}
