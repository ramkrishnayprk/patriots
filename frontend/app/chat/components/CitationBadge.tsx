import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { ChatSource } from "@/lib/chat/types";
import { hostname } from "@/lib/markdown/stabilize";

interface CitationBadgeProps {
  n: number;
  source?: ChatSource;
  variant: "inline" | "list";
}

// The same badge is used both inline in prose ([1]) and in the sources
// footer list, so a reader can visually match one to the other at a glance.
// Resolved and unresolved states share identical dimensions — no layout
// shift when a citation flips from "sources haven't arrived yet" to
// "clickable" partway through a stream.
export default function CitationBadge({ n, source, variant }: CitationBadgeProps) {
  const baseSx = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: 17,
    height: 17,
    px: "4px",
    borderRadius: "5px",
    fontSize: "0.6875rem",
    fontWeight: 700,
    lineHeight: 1,
    textDecoration: "none",
    flexShrink: 0,
    transition: "background-color 150ms, color 150ms, border-color 150ms",
    ...(variant === "inline"
      ? {
          verticalAlign: "super" as const,
          fontSize: "0.625rem",
          mx: "2px",
          position: "relative" as const,
          top: "0.05em",
        }
      : {}),
  };

  if (!source) {
    return (
      <Box
        component="span"
        sx={{
          ...baseSx,
          bgcolor: "rgba(255,255,255,0.06)",
          color: "text.secondary",
          border: "1px solid",
          borderColor: "divider",
          cursor: "default",
        }}
      >
        {n}
      </Box>
    );
  }

  const badge = (
    <Box
      component={variant === "list" ? "span" : "a"}
      {...(variant === "inline" ? { href: source.url, target: "_blank", rel: "noreferrer noopener" } : {})}
      sx={{
        ...baseSx,
        bgcolor: "rgba(242,177,52,0.14)",
        color: "primary.light",
        border: "1px solid rgba(242,177,52,0.28)",
        cursor: "pointer",
        "&:hover": {
          bgcolor: "primary.main",
          color: "primary.contrastText",
          borderColor: "primary.main",
        },
      }}
    >
      {n}
    </Box>
  );

  if (variant === "list") return badge;

  return (
    <Tooltip
      placement="top"
      enterDelay={250}
      title={
        <Typography variant="caption" component="span" sx={{ display: "block" }}>
          <strong>{source.title}</strong>
          <br />
          {hostname(source.url)}
        </Typography>
      }
    >
      {badge}
    </Tooltip>
  );
}
