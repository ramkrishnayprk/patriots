import type { Components } from "react-markdown";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import MuiLink from "@mui/material/Link";
import CitationBadge from "./CitationBadge";
import type { ChatSource } from "@/lib/chat/types";

const MONO_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace";

function Heading1({ children }: { children?: React.ReactNode }) {
  return (
    <Typography component="h3" sx={{ fontSize: "1.15rem", fontWeight: 700, mt: 2, mb: 0.75, letterSpacing: "-0.01em" }}>
      {children}
    </Typography>
  );
}

function Heading2({ children }: { children?: React.ReactNode }) {
  return (
    <Typography component="h4" sx={{ fontSize: "1.05rem", fontWeight: 700, color: "primary.light", mt: 2, mb: 0.75 }}>
      {children}
    </Typography>
  );
}

function Heading3({ children }: { children?: React.ReactNode }) {
  return (
    <Typography component="h5" sx={{ fontSize: "0.95rem", fontWeight: 700, color: "text.primary", mt: 1.5, mb: 0.5 }}>
      {children}
    </Typography>
  );
}

// Static tag map — must stay a stable reference. Passing a fresh object
// literal to ReactMarkdown's `components` prop on every render remounts the
// entire markdown subtree (lost text selection, flicker on every streamed
// token), since React can't match component identity across renders.
export const BASE_COMPONENTS: Components = {
  p: ({ children }) => (
    <Typography component="p" variant="body1" sx={{ my: 1, lineHeight: 1.65 }}>
      {children}
    </Typography>
  ),
  h1: Heading1,
  h2: Heading2,
  h3: Heading3,
  h4: Heading3,
  h5: Heading3,
  h6: Heading3,
  strong: ({ children }) => (
    <Box component="strong" sx={{ fontWeight: 700 }}>
      {children}
    </Box>
  ),
  em: ({ children }) => (
    <Box component="em" sx={{ fontStyle: "italic" }}>
      {children}
    </Box>
  ),
  del: ({ children }) => (
    <Box component="del" sx={{ textDecoration: "line-through", color: "text.secondary" }}>
      {children}
    </Box>
  ),
  ul: ({ children }) => (
    <Box
      component="ul"
      sx={{ my: 1, pl: 2.5, "& li::marker": { color: "primary.main" }, "& ul, & ol": { my: 0.5 } }}
    >
      {children}
    </Box>
  ),
  ol: ({ children }) => (
    <Box
      component="ol"
      sx={{
        my: 1,
        pl: 2.5,
        "& li::marker": { color: "primary.main", fontWeight: 700 },
        "& ul, & ol": { my: 0.5 },
      }}
    >
      {children}
    </Box>
  ),
  li: ({ children }) => (
    <Typography component="li" variant="body1" sx={{ my: 0.375, lineHeight: 1.6, pl: 0.5, "& > p": { my: 0 } }}>
      {children}
    </Typography>
  ),
  code: ({ children }) => (
    <Box
      component="code"
      sx={{
        px: 0.625,
        py: 0.125,
        borderRadius: 1,
        fontSize: "0.875em",
        fontFamily: MONO_FONT,
        bgcolor: "rgba(242,177,52,0.10)",
        color: "primary.light",
        border: "1px solid rgba(242,177,52,0.20)",
      }}
    >
      {children}
    </Box>
  ),
  pre: ({ children }) => (
    <Box
      component="pre"
      sx={{
        my: 1.25,
        p: 1.5,
        borderRadius: 2,
        bgcolor: "rgba(0,0,0,0.35)",
        border: "1px solid",
        borderColor: "divider",
        overflowX: "auto",
        fontSize: "0.8125rem",
        "& code": { bgcolor: "transparent", border: 0, p: 0, color: "text.primary", fontSize: "inherit" },
      }}
    >
      {children}
    </Box>
  ),
  blockquote: ({ children }) => (
    <Box
      component="blockquote"
      sx={{
        my: 1.25,
        ml: 0,
        pl: 1.5,
        borderLeft: "3px solid",
        borderColor: "secondary.main",
        color: "text.secondary",
        fontStyle: "italic",
        "& p": { my: 0.5 },
      }}
    >
      {children}
    </Box>
  ),
  hr: () => <Divider sx={{ my: 1.5, borderColor: "divider" }} />,
  table: ({ children }) => (
    <Box sx={{ my: 1.25, overflowX: "auto", border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
      <Box
        component="table"
        sx={{ borderCollapse: "collapse", width: "100%", fontSize: "0.875rem", "& tr:last-of-type td": { borderBottom: 0 } }}
      >
        {children}
      </Box>
    </Box>
  ),
  th: ({ children }) => (
    <Box
      component="th"
      sx={{
        textAlign: "left",
        px: 1.25,
        py: 0.75,
        fontWeight: 700,
        fontSize: "0.75rem",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        color: "primary.light",
        bgcolor: "rgba(242,177,52,0.06)",
        borderBottom: "1px solid",
        borderColor: "divider",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </Box>
  ),
  td: ({ children }) => (
    <Box
      component="td"
      sx={{ px: 1.25, py: 0.75, borderBottom: "1px solid", borderColor: "divider", verticalAlign: "top" }}
    >
      {children}
    </Box>
  ),
  img: () => null,
  input: () => null,
};

// The only sources-dependent entry — kept out of BASE_COMPONENTS so the
// static map never needs to change identity, and memoized by the caller
// keyed on `sources`.
export function createLinkComponent(sources?: ChatSource[]) {
  return function LinkComponent({ href, children }: { href?: string; children?: React.ReactNode }) {
    if (href?.startsWith("#cite-")) {
      const n = Number(href.slice(6));
      return <CitationBadge n={n} source={sources?.[n - 1]} variant="inline" />;
    }
    return (
      <MuiLink
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        underline="hover"
        sx={{ color: "primary.light", fontWeight: 500, textUnderlineOffset: "2px" }}
      >
        {children}
      </MuiLink>
    );
  };
}
