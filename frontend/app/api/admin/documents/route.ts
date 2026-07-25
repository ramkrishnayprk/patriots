import { NextResponse } from "next/server";
import { getAdminDocuments } from "@/lib/dummy/admin";

export async function GET() {
  return NextResponse.json({ documents: getAdminDocuments() });
}
