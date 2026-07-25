import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Avatar from "@mui/material/Avatar";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import type { ChatMessage } from "@/lib/chat/types";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const visibleContent = isUser
    ? message.content
    : message.content.replace(/\s*(?:\[\d+\])+/g, "").trim();

  return (
    <Stack direction="row" spacing={1.5} sx={{ justifyContent: isUser ? "flex-end" : "flex-start", width: "100%" }}>
      {!isUser && (
        <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.main" }}>
          <SmartToyOutlinedIcon fontSize="small" />
        </Avatar>
      )}
      <Box sx={{ maxWidth: "72%" }}>
        <Paper
          elevation={0}
          sx={{
            px: 2,
            py: 1.25,
            borderRadius: 3,
            bgcolor: isUser ? "primary.main" : "background.paper",
            color: isUser ? "primary.contrastText" : "text.primary",
            border: isUser ? "none" : "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
            {visibleContent}
          </Typography>
        </Paper>
        {!isUser && message.sources && message.sources.length > 0 && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Sources
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", mt: 0.5, gap: 1 }}>
              {message.sources.map((s) => (
                <Chip
                  key={s.id}
                  component="a"
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  clickable
                  label={s.title}
                  size="small"
                  variant="outlined"
                  sx={{ borderColor: "primary.main", color: "primary.light" }}
                />
              ))}
            </Stack>
          </Box>
        )}
      </Box>
    </Stack>
  );
}
