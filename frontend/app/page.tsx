"use client";

import Link from "next/link";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import TheatersRoundedIcon from "@mui/icons-material/TheatersRounded";

export default function Home() {
  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "linear-gradient(180deg, #16161C 0%, #0F0F13 55%, #050506 100%)",
        color: "#fff",
      }}
    >
      <Container maxWidth="md" sx={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", py: 10 }}>
        <Stack spacing={4} sx={{ alignItems: "center", textAlign: "center" }}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <TheatersRoundedIcon sx={{ fontSize: 36, color: "primary.main" }} />
            <Chip
              label="TMDB + IMDb powered"
              sx={{
                bgcolor: "rgba(255,255,255,0.08)",
                color: "primary.light",
                fontWeight: 600,
                border: "1px solid rgba(242,177,52,0.4)",
              }}
            />
          </Stack>

          <Typography variant="h2" sx={{ fontWeight: 700, fontSize: { xs: "2.25rem", sm: "3rem" } }}>
            Ask anything about movies &amp; TV
          </Typography>

          <Typography variant="h6" sx={{ color: "rgba(255,255,255,0.75)", fontWeight: 400, maxWidth: 560 }}>
            A RAG-powered assistant grounded in TMDB and IMDb data — cast,
            crew, ratings, box office, and release dates, answered with
            cited sources.
          </Typography>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ pt: 2 }}>
            <Button
              component={Link}
              href="/chat"
              variant="contained"
              size="large"
              color="primary"
              startIcon={<ForumRoundedIcon />}
              sx={{ px: 4, py: 1.5, fontSize: "1rem" }}
            >
              Start chatting
            </Button>
            <Button
              component={Link}
              href="/admin"
              variant="outlined"
              size="large"
              startIcon={<AdminPanelSettingsRoundedIcon />}
              sx={{
                px: 4,
                py: 1.5,
                fontSize: "1rem",
                color: "#fff",
                borderColor: "rgba(255,255,255,0.4)",
                "&:hover": { borderColor: "#fff", bgcolor: "rgba(255,255,255,0.06)" },
              }}
            >
              Go to Admin
            </Button>
          </Stack>
        </Stack>
      </Container>

      <Box component="footer" sx={{ py: 3, textAlign: "center", color: "rgba(255,255,255,0.5)", fontSize: "0.8rem" }}>
        <Typography variant="inherit" component="p" sx={{ m: 0 }}>
          Prototype UI — responses are illustrative, not live data.
        </Typography>
        <Typography variant="inherit" component="p" sx={{ m: 0, mt: 0.5 }}>
          Developed by <Box component="span" sx={{ color: "primary.light", fontWeight: 600 }}>Patriots</Box>
        </Typography>
      </Box>
    </Box>
  );
}
