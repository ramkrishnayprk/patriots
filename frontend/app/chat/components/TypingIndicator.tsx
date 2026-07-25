import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";

const dotSx = {
  width: 6,
  height: 6,
  borderRadius: "50%",
  bgcolor: "text.secondary",
  animation: "rag-typing-bounce 1.2s infinite ease-in-out",
};

export default function TypingIndicator() {
  return (
    <Stack direction="row" spacing={1.5}>
      <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.main" }}>
        <SmartToyOutlinedIcon fontSize="small" />
      </Avatar>
      <Paper
        elevation={0}
        sx={{ px: 2, py: 1.5, borderRadius: 3, border: "1px solid", borderColor: "divider" }}
      >
        <Stack direction="row" spacing={0.5}>
          <Box sx={{ ...dotSx, animationDelay: "0s" }} />
          <Box sx={{ ...dotSx, animationDelay: "0.15s" }} />
          <Box sx={{ ...dotSx, animationDelay: "0.3s" }} />
        </Stack>
        <style>{`
          @keyframes rag-typing-bounce {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
            30% { transform: translateY(-4px); opacity: 1; }
          }
        `}</style>
      </Paper>
    </Stack>
  );
}
