"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Fade from "@mui/material/Fade";
import MuiLink from "@mui/material/Link";
import MenuBookRoundedIcon from "@mui/icons-material/MenuBookRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import CitationBadge from "./CitationBadge";
import { hostname } from "@/lib/markdown/stabilize";
import type { ChatSource } from "@/lib/chat/types";

const MAX_VISIBLE = 3;

// The number badge here is the exact same CitationBadge used inline in the
// message text, so a reader can match "[2]" in a sentence to row 2 here at
// a glance — that pairing is the whole point of this footer.
export default function SourcesFooter({ sources }: { sources?: ChatSource[] }) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  const visible = expanded ? sources : sources.slice(0, MAX_VISIBLE);
  const hasMore = sources.length > MAX_VISIBLE;

  return (
    <Fade in timeout={220}>
      <Box sx={{ mt: 1 }}>
        <Stack direction="row" sx={{ alignItems: "center", gap: 0.75, mb: 0.75 }}>
          <MenuBookRoundedIcon sx={{ fontSize: 14, color: "text.secondary" }} />
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}
          >
            Sources · {sources.length}
          </Typography>
        </Stack>

        <Stack spacing={0.5}>
          {visible.map((s, i) => (
            <MuiLink
              key={s.id}
              id={`cite-${i + 1}`}
              component="a"
              href={s.url}
              target="_blank"
              rel="noreferrer noopener"
              underline="none"
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1,
                px: 1,
                py: 0.625,
                borderRadius: 1.5,
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "rgba(255,255,255,0.02)",
                transition: "background-color 150ms, border-color 150ms",
                "&:hover": {
                  bgcolor: "rgba(242,177,52,0.06)",
                  borderColor: "rgba(242,177,52,0.35)",
                  "& .cite-title": { color: "primary.light" },
                },
              }}
            >
              <CitationBadge n={i + 1} source={s} variant="list" />
              <Typography
                className="cite-title"
                variant="body2"
                noWrap
                sx={{ flex: 1, minWidth: 0, color: "text.primary", transition: "color 150ms" }}
              >
                {s.title}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary", flexShrink: 0 }}>
                {hostname(s.url)}
              </Typography>
              <OpenInNewRoundedIcon sx={{ fontSize: 13, color: "text.secondary", flexShrink: 0 }} />
            </MuiLink>
          ))}
        </Stack>

        {hasMore && (
          <Button
            size="small"
            onClick={() => setExpanded((v) => !v)}
            sx={{ color: "primary.light", fontWeight: 600, textTransform: "none", mt: 0.5, px: 1 }}
          >
            {expanded ? "Show fewer" : `Show all ${sources.length} sources`}
          </Button>
        )}
      </Box>
    </Fade>
  );
}
