"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Avatar from "@mui/material/Avatar";
import IconButton from "@mui/material/IconButton";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import MarkdownMessage from "./MarkdownMessage";
import SourcesFooter from "./SourcesFooter";
import type { ChatMessage } from "@/lib/chat/types";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (non-HTTPS/localhost, permissions) — no-op.
    }
  }

  return (
    <Stack direction="row" spacing={1.5} sx={{ justifyContent: isUser ? "flex-end" : "flex-start", width: "100%" }}>
      {!isUser && (
        <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.main" }}>
          <SmartToyOutlinedIcon fontSize="small" />
        </Avatar>
      )}
      <Box
        sx={{
          maxWidth: isUser ? "72%" : "min(88%, 720px)",
          "&:hover .msg-copy-btn": { opacity: 1 },
        }}
      >
        <Paper
          elevation={0}
          sx={{
            position: "relative",
            px: 2,
            py: 1.25,
            borderRadius: 3,
            bgcolor: isUser ? "primary.main" : "background.paper",
            color: isUser ? "primary.contrastText" : "text.primary",
            border: isUser ? "none" : "1px solid",
            borderColor: "divider",
          }}
        >
          {isUser ? (
            <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
              {message.content}
            </Typography>
          ) : (
            <MarkdownMessage content={message.content} sources={message.sources} isStreaming={isStreaming} />
          )}

          {!isUser && !isStreaming && (
            <IconButton
              className="msg-copy-btn"
              size="small"
              onClick={handleCopy}
              aria-label="Copy message"
              sx={{
                position: "absolute",
                top: 4,
                right: 4,
                opacity: 0,
                transition: "opacity 150ms",
                color: "text.secondary",
                "@media (hover: none)": { opacity: 1 },
              }}
            >
              {copied ? <CheckRoundedIcon fontSize="inherit" /> : <ContentCopyRoundedIcon fontSize="inherit" />}
            </IconButton>
          )}
        </Paper>

        {!isUser && <SourcesFooter sources={message.sources} messageId={message.id} />}
      </Box>
    </Stack>
  );
}
