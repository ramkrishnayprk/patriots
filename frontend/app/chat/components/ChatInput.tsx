"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import SendRoundedIcon from "@mui/icons-material/SendRounded";

interface Props {
  disabled: boolean;
  onSend: (text: string) => void;
}

export default function ChatInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <Box sx={{ px: 3, pb: 3, pt: 1 }}>
      <Paper
        elevation={0}
        sx={{
          display: "flex",
          alignItems: "flex-end",
          gap: 1,
          p: 1,
          borderRadius: 3,
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <TextField
          fullWidth
          multiline
          maxRows={6}
          placeholder="Ask about cast, ratings, box office, release dates..."
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          variant="standard"
          slotProps={{ input: { disableUnderline: true, sx: { px: 1 } } }}
        />
        <IconButton color="primary" disabled={disabled || !value.trim()} onClick={submit} sx={{ mb: 0.5 }}>
          <SendRoundedIcon />
        </IconButton>
      </Paper>
    </Box>
  );
}
