"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Avatar from "@mui/material/Avatar";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import LogoutRoundedIcon from "@mui/icons-material/LogoutRounded";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import TheatersRoundedIcon from "@mui/icons-material/TheatersRounded";
import type { Conversation } from "@/lib/chat/types";
import type { ChatModel } from "@/lib/chat/models";
import type { CurrentUser } from "@/lib/auth";

const SIDEBAR_WIDTH = 300;

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  models: ChatModel[];
  selectedModelId: string;
  onSelectModel: (id: string) => void;
  user: CurrentUser;
  onLogout: () => void;
  disabled: boolean;
}

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
  onRename,
  models,
  selectedModelId,
  onSelectModel,
  user,
  onLogout,
  disabled,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [modelMenuAnchor, setModelMenuAnchor] = useState<null | HTMLElement>(null);
  const [profileMenuAnchor, setProfileMenuAnchor] = useState<null | HTMLElement>(null);

  const selectedModel = models.find((m) => m.id === selectedModelId) ?? models[0];

  function startEdit(conv: Conversation) {
    setEditingId(conv.id);
    setEditValue(conv.title);
  }

  function commitEdit() {
    if (editingId && editValue.trim()) {
      onRename(editingId, editValue.trim());
    }
    setEditingId(null);
  }

  return (
    <Box
      sx={{
        width: SIDEBAR_WIDTH,
        flexShrink: 0,
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#111117",
        color: "#fff",
        borderRight: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", px: 2, pt: 2, pb: 1 }}>
        <TheatersRoundedIcon sx={{ color: "primary.main" }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          Cinebot
        </Typography>
      </Stack>

      <Box sx={{ px: 2, pb: 1 }}>
        <Button
          fullWidth
          variant="outlined"
          startIcon={<AddRoundedIcon />}
          onClick={onNewChat}
          disabled={disabled}
          sx={{
            justifyContent: "flex-start",
            color: "#fff",
            borderColor: "rgba(255,255,255,0.25)",
            "&:hover": { borderColor: "primary.main", bgcolor: "rgba(255,255,255,0.06)" },
          }}
        >
          New chat
        </Button>
      </Box>

      <Box sx={{ px: 2, pb: 1 }}>
        <Button
          fullWidth
          onClick={(e) => setModelMenuAnchor(e.currentTarget)}
          endIcon={<ExpandMoreRoundedIcon />}
          sx={{
            justifyContent: "space-between",
            color: "rgba(255,255,255,0.85)",
            textTransform: "none",
            border: "1px solid rgba(255,255,255,0.1)",
            px: 1.5,
          }}
        >
          <Stack sx={{ alignItems: "flex-start", overflow: "hidden" }}>
            <Typography variant="caption" sx={{ color: "rgba(255,255,255,0.5)", lineHeight: 1 }}>
              Model
            </Typography>
            <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
              {selectedModel?.label}
            </Typography>
          </Stack>
        </Button>
        <Menu
          anchorEl={modelMenuAnchor}
          open={Boolean(modelMenuAnchor)}
          onClose={() => setModelMenuAnchor(null)}
          slotProps={{ paper: { sx: { width: SIDEBAR_WIDTH - 32 } } }}
        >
          {models.map((m) => (
            <MenuItem
              key={m.id}
              selected={m.id === selectedModelId}
              onClick={() => {
                onSelectModel(m.id);
                setModelMenuAnchor(null);
              }}
            >
              <Stack sx={{ width: "100%" }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {m.label}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {m.description}
                </Typography>
              </Stack>
            </MenuItem>
          ))}
        </Menu>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.08)", my: 1 }} />

      <List
        subheader={
          <ListSubheader
            component="div"
            sx={{ bgcolor: "transparent", color: "rgba(255,255,255,0.5)", lineHeight: "32px" }}
          >
            History
          </ListSubheader>
        }
        sx={{ flex: 1, overflowY: "auto", px: 1 }}
      >
        {conversations.length === 0 && (
          <Typography variant="body2" sx={{ color: "rgba(255,255,255,0.4)", px: 2, py: 1 }}>
            No conversations yet.
          </Typography>
        )}
        {conversations.map((conv) => {
          const isEditing = editingId === conv.id;
          const isActive = conv.id === activeId;
          return (
            <ListItemButton
              key={conv.id}
              selected={isActive}
              onClick={() => !isEditing && onSelect(conv.id)}
              sx={{
                borderRadius: 1.5,
                mb: 0.5,
                "&.Mui-selected": { bgcolor: "rgba(242,177,52,0.18)" },
                "&:hover .conv-actions": { opacity: 1 },
              }}
            >
              {isEditing ? (
                <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", width: "100%" }} onClick={(e) => e.stopPropagation()}>
                  <TextField
                    autoFocus
                    size="small"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitEdit();
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    sx={{
                      "& .MuiInputBase-input": { color: "#fff", py: 0.5 },
                      "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.3)" },
                    }}
                    fullWidth
                  />
                  <IconButton size="small" onClick={commitEdit} sx={{ color: "primary.main" }}>
                    <CheckRoundedIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" onClick={() => setEditingId(null)} sx={{ color: "rgba(255,255,255,0.6)" }}>
                    <CloseRoundedIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ) : (
                <>
                  <ListItemText
                    primary={conv.title}
                    secondary={relativeTime(conv.updatedAt)}
                    slotProps={{
                      primary: { noWrap: true, sx: { fontSize: "0.875rem" } },
                      secondary: { sx: { color: "rgba(255,255,255,0.45)", fontSize: "0.7rem" } },
                    }}
                  />
                  <Stack
                    direction="row"
                    className="conv-actions"
                    sx={{ opacity: 0, transition: "opacity 0.15s" }}
                  >
                    <Tooltip title="Rename">
                      <IconButton
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          startEdit(conv);
                        }}
                        sx={{ color: "rgba(255,255,255,0.6)" }}
                      >
                        <EditOutlinedIcon fontSize="inherit" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(conv.id);
                        }}
                        sx={{ color: "rgba(255,255,255,0.6)", "&:hover": { color: "#ff8a80" } }}
                      >
                        <DeleteOutlineRoundedIcon fontSize="inherit" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </>
              )}
            </ListItemButton>
          );
        })}
      </List>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

      <Button
        onClick={(e) => setProfileMenuAnchor(e.currentTarget)}
        sx={{
          m: 1,
          justifyContent: "flex-start",
          textTransform: "none",
          color: "#fff",
          "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
        }}
      >
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", width: "100%" }}>
          <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.main", color: "primary.contrastText", fontSize: "0.8rem", fontWeight: 700 }}>
            {user.initials}
          </Avatar>
          <Stack sx={{ alignItems: "flex-start", overflow: "hidden" }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
              {user.name}
            </Typography>
            <Typography variant="caption" noWrap sx={{ color: "rgba(255,255,255,0.5)" }}>
              {user.email}
            </Typography>
          </Stack>
        </Stack>
      </Button>
      <Menu anchorEl={profileMenuAnchor} open={Boolean(profileMenuAnchor)} onClose={() => setProfileMenuAnchor(null)}>
        <MenuItem onClick={() => setProfileMenuAnchor(null)}>
          <ListItemIcon>
            <SettingsOutlinedIcon fontSize="small" />
          </ListItemIcon>
          Settings
        </MenuItem>
        <MenuItem
          onClick={() => {
            setProfileMenuAnchor(null);
            onLogout();
          }}
        >
          <ListItemIcon>
            <LogoutRoundedIcon fontSize="small" />
          </ListItemIcon>
          Log out
        </MenuItem>
      </Menu>
    </Box>
  );
}

export { SIDEBAR_WIDTH };
