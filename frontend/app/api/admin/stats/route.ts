import { NextResponse } from "next/server";
import { getAdminStats } from "@/lib/dummy/admin";

export async function GET() {
  return NextResponse.json({ stats: getAdminStats() });
}
