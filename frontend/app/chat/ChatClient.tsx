"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Sidebar from "./components/Sidebar";
import MessageBubble from "./components/MessageBubble";
import TypingIndicator from "./components/TypingIndicator";
import ChatInput from "./components/ChatInput";
import { readSSE } from "@/lib/sse";
import { CURRENT_USER } from "@/lib/dummy/user";
import type { ChatMessage, ChatSource, Conversation } from "@/lib/dummy/conversations";
import type { ChatModel } from "@/lib/dummy/models";

export default function ChatClient() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [models, setModels] = useState<ChatModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [loaded, setLoaded] = useState(false);

  const [streamingText, setStreamingText] = useState("");
  const [streamingSources, setStreamingSources] = useState<ChatSource[] | null>(null);
  const [isWaiting, setIsWaiting] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function bootstrap() {
      const [modelsRes, convRes] = await Promise.all([fetch("/api/models"), fetch("/api/conversations")]);
      const modelsData = await modelsRes.json();
      const convData = await convRes.json();
      setModels(modelsData.models);
      setSelectedModelId(modelsData.models[0]?.id ?? "");
      setConversations(convData.conversations);
      setActiveId(convData.conversations[0]?.id ?? null);
      setLoaded(true);
    }
    bootstrap();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [conversations, activeId, streamingText]);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  async function handleNewChat() {
    const res = await fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modelId: selectedModelId }),
    });
    const { conversation } = await res.json();
    setConversations((prev) => [conversation, ...prev]);
    setActiveId(conversation.id);
  }

  async function handleDelete(id: string) {
    await fetch(`/api/conversations/${id}`, { method: "DELETE" });
    const remaining = conversations.filter((c) => c.id !== id);
    setConversations(remaining);
    if (activeId === id) {
      setActiveId(remaining[0]?.id ?? null);
    }
  }

  async function handleRename(id: string, title: string) {
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)));
    await fetch(`/api/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  }

  async function handleSend(text: string) {
    let conversationId = activeId;

    if (!conversationId) {
      const res = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelId: selectedModelId }),
      });
      const { conversation } = await res.json();
      conversationId = conversation.id;
      setConversations((prev) => [conversation, ...prev]);
      setActiveId(conversation.id);
    }

    const userMessage: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      createdAt: new Date().toISOString(),
    };
    setConversations((prev) =>
      prev.map((c) => (c.id === conversationId ? { ...c, messages: [...c.messages, userMessage] } : c)),
    );

    setIsWaiting(true);
    setStreamingText("");
    setStreamingSources(null);

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversationId, message: text }),
    });

    if (!res.ok || !res.body) {
      setIsWaiting(false);
      return;
    }

    let acc = "";
    let sources: ChatSource[] | undefined;

    for await (const event of readSSE(res)) {
      if (event.type === "delta") {
        setIsWaiting(false);
        setIsStreaming(true);
        acc += event.text as string;
        setStreamingText(acc);
      } else if (event.type === "sources") {
        sources = event.sources as ChatSource[];
        setStreamingSources(sources);
      } else if (event.type === "done") {
        const assistantMessage: ChatMessage = {
          id: `local-${Date.now()}-a`,
          role: "assistant",
          content: acc,
          createdAt: new Date().toISOString(),
          sources,
        };
        setConversations((prev) =>
          prev.map((c) =>
            c.id === conversationId
              ? { ...c, messages: [...c.messages, assistantMessage], updatedAt: assistantMessage.createdAt }
              : c,
          ),
        );
        setIsStreaming(false);
        setIsWaiting(false);
        setStreamingText("");
        setStreamingSources(null);
      }
    }
  }

  if (!loaded) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <CircularProgress color="primary" />
      </Box>
    );
  }

  return (
    <Stack direction="row" sx={{ height: "100vh", overflow: "hidden" }}>
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNewChat={handleNewChat}
        onDelete={handleDelete}
        onRename={handleRename}
        models={models}
        selectedModelId={selectedModelId}
        onSelectModel={setSelectedModelId}
        user={CURRENT_USER}
      />

      <Stack sx={{ flex: 1, height: "100vh", bgcolor: "background.default" }}>
        <Stack
          direction="row"
          sx={{ alignItems: "center", justifyContent: "space-between", px: 3, py: 2, borderBottom: "1px solid", borderColor: "divider" }}
        >
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }} noWrap>
            {active?.title ?? "New chat"}
          </Typography>
          <Chip
            size="small"
            label={models.find((m) => m.id === selectedModelId)?.label ?? ""}
            sx={{ bgcolor: "rgba(242,177,52,0.12)", color: "primary.main", fontWeight: 600 }}
          />
        </Stack>

        <Box ref={scrollRef} sx={{ flex: 1, overflowY: "auto", px: 3, py: 3 }}>
          <Stack spacing={2.5} sx={{ maxWidth: 820, mx: "auto" }}>
            {(!active || active.messages.length === 0) && !isWaiting && !isStreaming && (
              <Box sx={{ textAlign: "center", color: "text.secondary", mt: 8 }}>
                <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                  Ask about movies &amp; TV shows
                </Typography>
                <Typography variant="body2">
                  Try: &ldquo;Who directed Oppenheimer and what&apos;s the runtime?&rdquo;
                </Typography>
              </Box>
            )}

            {active?.messages.map((m) => <MessageBubble key={m.id} message={m} />)}

            {isWaiting && <TypingIndicator />}

            {isStreaming && (
              <MessageBubble
                message={{
                  id: "streaming",
                  role: "assistant",
                  content: streamingText,
                  createdAt: new Date().toISOString(),
                  sources: streamingSources ?? undefined,
                }}
              />
            )}
          </Stack>
        </Box>

        <ChatInput disabled={isWaiting || isStreaming} onSend={handleSend} />
      </Stack>
    </Stack>
  );
}
