import { NextResponse } from "next/server";
import { getAdminUsers } from "@/lib/dummy/admin";

export async function GET() {
  return NextResponse.json({ users: getAdminUsers() });
}
