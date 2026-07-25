"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Sidebar from "./components/Sidebar";
import MessageBubble from "./components/MessageBubble";
import TypingIndicator from "./components/TypingIndicator";
import ChatInput from "./components/ChatInput";
import {
  getCurrentUser,
  logout,
  subscribeToAuthChanges,
  isWelcomePending,
  clearWelcomePending,
  type CurrentUser,
} from "@/lib/auth";
import type {
  ChatMessage,
  Conversation,
} from "@/lib/chat/types";
import type { ChatModel } from "@/lib/chat/models";

export default function ChatClient() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showWelcome, setShowWelcome] = useState(false);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draftMessages, setDraftMessages] = useState<ChatMessage[]>([]);
  const [models, setModels] = useState<ChatModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [isWaiting, setIsWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const current = getCurrentUser();
    if (!current) {
      router.replace("/");
      return;
    }
    setUser(current);
    setAuthChecked(true);
    if (isWelcomePending()) setShowWelcome(true);
  }, [router]);

  useEffect(() => {
    if (!authChecked) return;
    return subscribeToAuthChanges(() => {
      if (!getCurrentUser()) router.replace("/");
    });
  }, [authChecked, router]);

  useEffect(() => {
    if (!authChecked || !user) return;

    async function bootstrap() {
      try {
        const [modelsResponse, conversationsResponse] = await Promise.all([
          fetch("/api/models", { cache: "no-store" }),
          fetch("/api/conversations", { cache: "no-store" }),
        ]);
        if (!modelsResponse.ok || !conversationsResponse.ok) {
          throw new Error("The chat service could not be loaded.");
        }
        const modelsData = await modelsResponse.json();
        const conversationsData = await conversationsResponse.json();
        const availableModels = Array.isArray(modelsData.models)
          ? modelsData.models
          : [];
        const availableConversations = Array.isArray(
          conversationsData.conversations,
        )
          ? conversationsData.conversations
          : [];
        setModels(availableModels);
        setSelectedModelId(availableModels[0]?.id ?? "");
        setConversations(availableConversations);
        setActiveId(availableConversations[0]?.id ?? null);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "The chat service could not be loaded.",
        );
      } finally {
        setLoaded(true);
      }
    }
    void bootstrap();
  }, [authChecked, user]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [conversations, activeId, draftMessages, isWaiting]);

  const active = conversations.find((conversation) => conversation.id === activeId) ?? null;
  const visibleMessages = active?.messages ?? draftMessages;

  function dismissWelcome() {
    setShowWelcome(false);
    clearWelcomePending();
  }

  function handleLogout() {
    logout();
    router.replace("/");
  }

  function handleNewChat() {
    if (isWaiting) return;
    setActiveId(null);
    setDraftMessages([]);
    setError(null);
  }

  function handleSelect(id: string) {
    if (isWaiting) return;
    setActiveId(id);
    setDraftMessages([]);
    setError(null);
  }

  async function handleDelete(id: string) {
    if (isWaiting) return;
    setError(null);
    const response = await fetch(`/api/conversations/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.error || "The conversation could not be deleted.");
      return;
    }
    const remaining = conversations.filter((conversation) => conversation.id !== id);
    setConversations(remaining);
    if (activeId === id) {
      setActiveId(remaining[0]?.id ?? null);
    }
  }

  async function handleRename(id: string, title: string) {
    setError(null);
    const response = await fetch(`/api/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(payload.error || "The conversation could not be renamed.");
      return;
    }
    const updated = payload.conversation as Conversation;
    setConversations((current) =>
      current.map((conversation) =>
        conversation.id === updated.id ? updated : conversation,
      ),
    );
  }

  async function handleSend(text: string) {
    if (isWaiting) return;

    const conversationId = activeId;
    const optimisticMessage: ChatMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: text,
      createdAt: new Date().toISOString(),
    };
    if (conversationId) {
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                messages: [...conversation.messages, optimisticMessage],
              }
            : conversation,
        ),
      );
    } else {
      setDraftMessages([optimisticMessage]);
    }

    setError(null);
    setIsWaiting(true);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversationId,
          message: text,
          modelId: selectedModelId,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.conversation) {
        throw new Error(payload.error || "The assistant could not answer.");
      }

      const persisted = payload.conversation as Conversation;
      setConversations((current) => [
        persisted,
        ...current.filter((conversation) => conversation.id !== persisted.id),
      ]);
      setActiveId(persisted.id);
      setDraftMessages([]);
    } catch (sendError) {
      setError(
        sendError instanceof Error
          ? sendError.message
          : "The assistant could not answer.",
      );
    } finally {
      setIsWaiting(false);
    }
  }

  if (!authChecked || !loaded || !user) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
        }}
      >
        <CircularProgress color="primary" />
      </Box>
    );
  }

  return (
    <Stack direction="row" sx={{ height: "100vh", overflow: "hidden" }}>
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onNewChat={handleNewChat}
        onDelete={handleDelete}
        onRename={handleRename}
        models={models}
        selectedModelId={selectedModelId}
        onSelectModel={setSelectedModelId}
        user={user}
        onLogout={handleLogout}
        disabled={isWaiting}
      />

      <Stack sx={{ flex: 1, height: "100vh", bgcolor: "background.default" }}>
        <Stack
          direction="row"
          sx={{
            alignItems: "center",
            justifyContent: "space-between",
            px: 3,
            py: 2,
            borderBottom: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }} noWrap>
            {active?.title ?? "New chat"}
          </Typography>
          <Chip
            size="small"
            label={models.find((model) => model.id === selectedModelId)?.label ?? ""}
            sx={{
              bgcolor: "rgba(242,177,52,0.12)",
              color: "primary.main",
              fontWeight: 600,
            }}
          />
        </Stack>

        <Box ref={scrollRef} sx={{ flex: 1, overflowY: "auto", px: 3, py: 3 }}>
          <Stack spacing={2.5} sx={{ maxWidth: 820, mx: "auto" }}>
            {visibleMessages.length === 0 && !isWaiting && (
              <Box sx={{ textAlign: "center", color: "text.secondary", mt: 8 }}>
                <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                  Welcome to Cinebot
                </Typography>
                <Typography variant="body1" sx={{ mb: 1 }}>
                  Ask about 2026 movies, ratings, genres, cast, directors, or plots.
                </Typography>
                <Typography variant="body2">
                  Try: &ldquo;What are the best science fiction movies?&rdquo;
                </Typography>
              </Box>
            )}

            {visibleMessages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {isWaiting && <TypingIndicator />}

            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </Box>

        <ChatInput disabled={isWaiting} onSend={handleSend} />
      </Stack>

      <Snackbar
        open={showWelcome}
        autoHideDuration={5000}
        onClose={(_event, reason) => {
          if (reason === "clickaway") return;
          dismissWelcome();
        }}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
      >
        <Alert onClose={dismissWelcome} severity="success" variant="filled" sx={{ bgcolor: "primary.main", color: "primary.contrastText" }}>
          Welcome, {user.name}!
        </Alert>
      </Snackbar>
    </Stack>
  );
}
