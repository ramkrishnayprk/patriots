"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import AuthDialog from "./AuthDialog";
import { getCurrentUser, hasAnyUsers, type CurrentUser } from "@/lib/auth";

// Continuous cursor-driven color blend between "chat" (gold, split=0) and
// "admin" (crimson, split=1), lerped toward a target every frame via
// requestAnimationFrame and written straight to CSS custom properties on
// the panel DOM node — no React re-renders on pointer move. Keyboard focus
// drives the same loop toward split=0/1 so focus gets identical motion to
// hover, not a degraded fallback. See the plan doc for the full rationale.

const GOLD = "242,177,52";
const CRIMSON = "230,57,70";
const LERP = 0.15;
const SETTLE_EPSILON = 0.002;

interface PointerState {
  x: number;
  y: number;
  split: number;
  tx: number;
  ty: number;
  tsplit: number;
}

export default function HeroSplitPanel() {
  const router = useRouter();
  const panelRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<PointerState>({ x: 0.5, y: 0.5, split: 0.5, tx: 0.5, ty: 0.5, tsplit: 0.5 });
  const rafRef = useRef<number | null>(null);
  const interactiveRef = useRef(false);
  const [supportsHover, setSupportsHover] = useState(true);
  const [authDialogOpen, setAuthDialogOpen] = useState(false);
  const [authInitialMode, setAuthInitialMode] = useState<"signup" | "login">("signup");

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hoverCapable = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    interactiveRef.current = !reducedMotion && hoverCapable;
    setSupportsHover(hoverCapable);

    if (panelRef.current) {
      panelRef.current.style.setProperty("--x", "50%");
      panelRef.current.style.setProperty("--y", "50%");
      panelRef.current.style.setProperty("--split", "0.5");
    }

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  function applyActiveZoneAttr(split: number) {
    if (!panelRef.current) return;
    const zone = split < 0.5 ? "chat" : "admin";
    if (panelRef.current.dataset.activeZone !== zone) {
      panelRef.current.dataset.activeZone = zone;
    }
  }

  function tick() {
    const s = stateRef.current;
    const dx = s.tx - s.x;
    const dy = s.ty - s.y;
    const dsplit = s.tsplit - s.split;

    if (Math.abs(dx) < SETTLE_EPSILON && Math.abs(dy) < SETTLE_EPSILON && Math.abs(dsplit) < SETTLE_EPSILON) {
      s.x = s.tx;
      s.y = s.ty;
      s.split = s.tsplit;
      writeStyle();
      rafRef.current = null;
      return;
    }

    s.x += dx * LERP;
    s.y += dy * LERP;
    s.split += dsplit * LERP;
    writeStyle();
    rafRef.current = requestAnimationFrame(tick);
  }

  function writeStyle() {
    const panel = panelRef.current;
    if (!panel) return;
    const s = stateRef.current;
    panel.style.setProperty("--x", `${s.x * 100}%`);
    panel.style.setProperty("--y", `${s.y * 100}%`);
    panel.style.setProperty("--split", String(s.split));
    applyActiveZoneAttr(s.split);
  }

  function startLoop() {
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }

  function setTarget(tx: number, ty: number, tsplit: number) {
    if (!interactiveRef.current) {
      // Reduced motion / touch: snap instantly, no lerp loop.
      stateRef.current = { x: tx, y: ty, split: tsplit, tx, ty, tsplit };
      writeStyle();
      return;
    }
    stateRef.current.tx = tx;
    stateRef.current.ty = ty;
    stateRef.current.tsplit = tsplit;
    startLoop();
  }

  function handlePointerMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!interactiveRef.current || !panelRef.current) return;
    const rect = panelRef.current.getBoundingClientRect();
    const fx = clamp((e.clientX - rect.left) / rect.width, 0, 1);
    const fy = clamp((e.clientY - rect.top) / rect.height, 0, 1);
    setTarget(fx, fy, fx);
  }

  function handlePointerLeave() {
    setTarget(0.5, 0.5, 0.5);
  }

  function handleZoneFocus(zone: "chat" | "admin") {
    setTarget(zone === "chat" ? 0.25 : 0.75, 0.5, zone === "chat" ? 0 : 1);
  }

  function handleZoneBlur() {
    setTarget(0.5, 0.5, 0.5);
  }

  function handleChatZoneClick(e: React.MouseEvent) {
    // Checked only here (never during render/mount) — this component is
    // server-rendered for initial HTML, where localStorage doesn't exist;
    // an onClick handler only ever runs post-hydration, in the browser.
    if (getCurrentUser()) return; // real session — let the Link navigate normally
    e.preventDefault();
    setAuthInitialMode(hasAnyUsers() ? "login" : "signup");
    setAuthDialogOpen(true);
  }

  function handleAuthSuccess(_user: CurrentUser) {
    setAuthDialogOpen(false);
    router.push("/chat");
  }

  return (
    <Box
      ref={panelRef}
      onMouseMove={handlePointerMove}
      onMouseLeave={handlePointerLeave}
      sx={{
        position: "relative",
        width: "100%",
        maxWidth: 840,
        mx: "auto",
        borderRadius: 4,
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.1)",
        bgcolor: "rgba(22,22,28,0.6)",
        backdropFilter: "blur(20px)",
        // Faint always-on hint of "gold on the left, crimson on the right",
        // independent of pointer state.
        backgroundImage: `linear-gradient(90deg, rgba(${GOLD},0.08) 0%, transparent 45%, transparent 55%, rgba(${CRIMSON},0.08) 100%)`,
      }}
    >
      {/* Cursor-follow spotlights — continuous system, no CSS transition (smoothing happens in the JS lerp). */}
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          opacity: "calc(1 - var(--split))",
          background: `radial-gradient(420px circle at var(--x) var(--y), rgba(${GOLD},0.35), transparent 70%)`,
        }}
      />
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          opacity: "var(--split)",
          background: `radial-gradient(420px circle at var(--x) var(--y), rgba(${CRIMSON},0.35), transparent 70%)`,
        }}
      />

      {/* Divider — static visual anchor, not itself animated. */}
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: "50%",
          width: "1px",
          background: `linear-gradient(180deg, rgba(${GOLD},0.6), rgba(${CRIMSON},0.6))`,
          boxShadow: `0 0 24px rgba(${GOLD},0.15), 0 0 24px rgba(${CRIMSON},0.15)`,
          display: { xs: "none", sm: "block" },
        }}
      />

      <Stack direction={{ xs: "column", sm: "row" }} sx={{ position: "relative", zIndex: 1 }}>
        <HeroZone
          href="/chat"
          icon={<ForumRoundedIcon sx={{ fontSize: 36 }} />}
          title="Start chatting"
          description="Ask about cast, ratings, box office, release dates"
          accentRgb={GOLD}
          zoneKey="chat"
          supportsHover={supportsHover}
          onFocus={() => handleZoneFocus("chat")}
          onBlur={handleZoneBlur}
          onClick={handleChatZoneClick}
        />
        <HeroZone
          href="/admin"
          icon={<AdminPanelSettingsRoundedIcon sx={{ fontSize: 36 }} />}
          title="Go to Admin"
          description="Manage the indexed knowledge base and users"
          accentRgb={CRIMSON}
          zoneKey="admin"
          supportsHover={supportsHover}
          onFocus={() => handleZoneFocus("admin")}
          onBlur={handleZoneBlur}
        />
      </Stack>

      <AuthDialog
        open={authDialogOpen}
        initialMode={authInitialMode}
        onClose={() => setAuthDialogOpen(false)}
        onSuccess={handleAuthSuccess}
      />
    </Box>
  );
}

function HeroZone({
  href,
  icon,
  title,
  description,
  accentRgb,
  zoneKey,
  supportsHover,
  onFocus,
  onBlur,
  onClick,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  accentRgb: string;
  zoneKey: "chat" | "admin";
  supportsHover: boolean;
  onFocus: () => void;
  onBlur: () => void;
  onClick?: (e: React.MouseEvent) => void;
}) {
  const isChat = zoneKey === "chat";
  const dimmedOpacity = isChat ? "calc(0.55 + 0.45 * (1 - var(--split)))" : "calc(0.55 + 0.45 * var(--split))";
  const dataSelector = `[data-active-zone="${zoneKey}"] &`;

  return (
    <Box
      component={Link}
      href={href}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
      aria-label={isChat ? "Start chatting with Cinebot" : "Go to Cinebot admin panel"}
      sx={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        gap: 1,
        px: 4,
        py: { xs: 5, sm: 0 },
        minHeight: { xs: "auto", sm: 300 },
        textDecoration: "none",
        color: "inherit",
        cursor: "pointer",
        outlineOffset: -4,
        "&:focus-visible": {
          outline: `2px solid rgba(${accentRgb},0.9)`,
        },
        // Static per-zone tint for touch/no-hover devices, where the
        // cursor-follow spotlight system is never activated.
        ...(supportsHover
          ? {}
          : {
              background: `linear-gradient(${isChat ? "135deg" : "225deg"}, rgba(${accentRgb},0.12), transparent 70%)`,
            }),
      }}
    >
      <Box
        sx={{
          transition: "transform 300ms cubic-bezier(0.4,0,0.2,1), filter 300ms cubic-bezier(0.4,0,0.2,1)",
          color: `rgb(${accentRgb})`,
          [dataSelector]: {
            transform: "translateY(-2px) scale(1.06)",
            filter: "brightness(1.2)",
          },
        }}
      >
        {icon}
      </Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, color: "text.primary" }}>
        {title}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          color: "text.secondary",
          maxWidth: 260,
          opacity: supportsHover ? dimmedOpacity : 0.85,
          transition: "opacity 150ms ease",
        }}
      >
        {description}
      </Typography>
    </Box>
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
