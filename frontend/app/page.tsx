"use client";

import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import TheatersRoundedIcon from "@mui/icons-material/TheatersRounded";
import HeroSplitPanel from "./components/HeroSplitPanel";

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
      <Container maxWidth="md" sx={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", py: { xs: 6, sm: 8 } }}>
        <Stack spacing={{ xs: 3, sm: 3.5 }} sx={{ alignItems: "center", textAlign: "center" }}>
          <Stack
            direction="row"
            spacing={1.5}
            className="hero-fade-up"
            sx={{ alignItems: "center", animation: "hero-fade-up 500ms cubic-bezier(0.4,0,0.2,1) both" }}
          >
            <TheatersRoundedIcon sx={{ fontSize: 36, color: "primary.main" }} />
            <Typography
              variant="h5"
              sx={{ fontWeight: 800, letterSpacing: "-0.02em", color: "text.primary" }}
            >
              Cinebot
            </Typography>
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

          <Typography
            variant="h2"
            className="hero-fade-up"
            sx={{ fontWeight: 700, fontSize: { xs: "2.25rem", sm: "3rem" }, animation: "hero-fade-up 500ms cubic-bezier(0.4,0,0.2,1) 80ms both" }}
          >
            Ask anything about movies &amp; TV
          </Typography>

          <Typography
            variant="h6"
            className="hero-fade-up"
            sx={{
              color: "rgba(255,255,255,0.75)",
              fontWeight: 400,
              maxWidth: 560,
              animation: "hero-fade-up 500ms cubic-bezier(0.4,0,0.2,1) 160ms both",
            }}
          >
            A RAG-powered assistant grounded in TMDB and IMDb data — cast,
            crew, ratings, box office, and release dates, answered with
            cited sources.
          </Typography>

          <Box
            className="hero-fade-up"
            sx={{ width: "100%", pt: 1.5, animation: "hero-fade-up 500ms cubic-bezier(0.4,0,0.2,1) 240ms both" }}
          >
            <HeroSplitPanel />
          </Box>
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

      <style>{`
        @keyframes hero-fade-up {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .hero-fade-up { animation: none !important; opacity: 1 !important; transform: none !important; }
        }
      `}</style>
    </Box>
  );
}
