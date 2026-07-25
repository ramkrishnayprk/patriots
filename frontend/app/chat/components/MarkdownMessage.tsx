"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Typography from "@mui/material/Typography";
import { BASE_COMPONENTS, createLinkComponent } from "./markdownComponents";
import remarkCitations from "@/lib/markdown/remarkCitations";
import { stabilizeStreamingMarkdown } from "@/lib/markdown/stabilize";
import type { ChatSource } from "@/lib/chat/types";

interface MarkdownMessageProps {
  content: string;
  sources?: ChatSource[];
  isStreaming?: boolean;
}

const REMARK_PLUGINS = [remarkGfm, remarkCitations];

export default function MarkdownMessage({ content, sources, isStreaming }: MarkdownMessageProps) {
  const stabilized = useMemo(
    () => (isStreaming ? stabilizeStreamingMarkdown(content) : content),
    [content, isStreaming],
  );

  const components = useMemo(
    () => ({ ...BASE_COMPONENTS, a: createLinkComponent(sources) }),
    [sources],
  );

  return (
    <Typography
      component="div"
      variant="body1"
      data-streaming={isStreaming ? "true" : undefined}
      sx={{
        lineHeight: 1.65,
        wordBreak: "break-word",
        "& > *:first-child": { mt: 0 },
        "& > *:last-child": { mb: 0 },
        '&[data-streaming="true"] > *:last-child::after': {
          content: '""',
          display: "inline-block",
          width: "2px",
          height: "1em",
          bgcolor: "primary.main",
          ml: "3px",
          verticalAlign: "-0.15em",
          borderRadius: "1px",
          animation: "cinebot-caret 1s steps(1) infinite",
        },
        "@keyframes cinebot-caret": {
          "0%, 49%": { opacity: 1 },
          "50%, 100%": { opacity: 0 },
        },
        "@media (prefers-reduced-motion: reduce)": {
          '&[data-streaming="true"] > *:last-child::after': { animation: "none", opacity: 1 },
        },
      }}
    >
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={components}>
        {stabilized}
      </ReactMarkdown>
    </Typography>
  );
}
