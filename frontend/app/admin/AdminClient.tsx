"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Avatar from "@mui/material/Avatar";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MuiLink from "@mui/material/Link";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
import DescriptionRoundedIcon from "@mui/icons-material/DescriptionRounded";
import ChatBubbleOutlineRoundedIcon from "@mui/icons-material/ChatBubbleOutlineRounded";
import DataObjectRoundedIcon from "@mui/icons-material/DataObjectRounded";
import GroupRoundedIcon from "@mui/icons-material/GroupRounded";
import TheatersRoundedIcon from "@mui/icons-material/TheatersRounded";
import StatCard from "./components/StatCard";
import StatusChip from "./components/StatusChip";
import type { AdminDocument, AdminStats, AdminUser } from "@/lib/dummy/admin";

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const hours = Math.round(diffMs / 3_600_000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function AdminClient() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [documents, setDocuments] = useState<AdminDocument[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    async function load() {
      const [statsRes, docsRes, usersRes] = await Promise.all([
        fetch("/api/admin/stats"),
        fetch("/api/admin/documents"),
        fetch("/api/admin/users"),
      ]);
      const [statsData, docsData, usersData] = await Promise.all([statsRes.json(), docsRes.json(), usersRes.json()]);
      setStats(statsData.stats);
      setDocuments(docsData.documents);
      setUsers(usersData.users);
      setLoaded(true);
    }
    load();
  }, []);

  if (!loaded || !stats) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <CircularProgress color="primary" />
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", px: 4, py: 2, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}
      >
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
          <TheatersRoundedIcon color="primary" />
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Admin
          </Typography>
        </Stack>
        <Button component={Link} href="/chat" variant="outlined" startIcon={<ForumRoundedIcon />}>
          Go to Chat
        </Button>
      </Stack>

      <Box sx={{ px: 4, py: 4, maxWidth: 1200, mx: "auto" }}>
        <Stack direction="row" sx={{ flexWrap: "wrap", gap: 2, mb: 4 }}>
          <StatCard label="Conversations" value={stats.totalConversations} icon={ChatBubbleOutlineRoundedIcon} />
          <StatCard label="Messages" value={stats.totalMessages} icon={ForumRoundedIcon} />
          <StatCard label="Indexed documents" value={stats.totalDocuments} icon={DescriptionRoundedIcon} />
          <StatCard label="Chunks" value={stats.totalChunks} icon={DataObjectRoundedIcon} />
          <StatCard label="Active users (7d)" value={stats.activeUsers7d} icon={GroupRoundedIcon} />
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 3 }}>
          Last ingest run: {relativeTime(stats.lastIngestAt)}
        </Typography>

        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.5 }}>
          Knowledge base documents
        </Typography>
        <TableContainer component={Paper} elevation={0} sx={{ border: "1px solid", borderColor: "divider", mb: 4 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Title</TableCell>
                <TableCell>Category</TableCell>
                <TableCell align="right">Chunks</TableCell>
                <TableCell>Last crawled</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {documents.map((doc) => (
                <TableRow key={doc.id} hover>
                  <TableCell>
                    <MuiLink href={doc.url} target="_blank" rel="noreferrer" underline="hover">
                      {doc.title}
                    </MuiLink>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={doc.category} variant="outlined" />
                  </TableCell>
                  <TableCell align="right">{doc.chunkCount}</TableCell>
                  <TableCell>{relativeTime(doc.lastCrawledAt)}</TableCell>
                  <TableCell>
                    <StatusChip status={doc.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.5 }}>
          Users
        </Typography>
        <TableContainer component={Paper} elevation={0} sx={{ border: "1px solid", borderColor: "divider" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>User</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Last active</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id} hover>
                  <TableCell>
                    <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                      <Avatar sx={{ width: 28, height: 28, fontSize: "0.75rem", bgcolor: "primary.main" }}>
                        {user.name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")}
                      </Avatar>
                      <Stack>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {user.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {user.email}
                        </Typography>
                      </Stack>
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ textTransform: "capitalize" }}>{user.role}</TableCell>
                  <TableCell>{relativeTime(user.lastActiveAt)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
    </Box>
  );
}
