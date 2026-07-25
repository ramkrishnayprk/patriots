import { NextResponse } from "next/server";
import { CHAT_MODELS } from "@/lib/dummy/models";

export async function GET() {
  return NextResponse.json({ models: CHAT_MODELS });
}
