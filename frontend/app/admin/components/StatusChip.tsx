import Chip from "@mui/material/Chip";
import type { AdminDocument } from "@/lib/dummy/admin";

const STYLES: Record<AdminDocument["status"], { label: string; bg: string; color: string }> = {
  indexed: { label: "Indexed", bg: "rgba(46,125,50,0.12)", color: "#2e7d32" },
  pending: { label: "Pending", bg: "rgba(201,162,75,0.18)", color: "#8a6d1f" },
  failed: { label: "Failed", bg: "rgba(211,47,47,0.12)", color: "#d32f2f" },
};

export default function StatusChip({ status }: { status: AdminDocument["status"] }) {
  const s = STYLES[status];
  return <Chip size="small" label={s.label} sx={{ bgcolor: s.bg, color: s.color, fontWeight: 600 }} />;
}
