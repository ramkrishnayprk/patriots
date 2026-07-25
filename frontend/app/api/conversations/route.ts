import { NextResponse } from "next/server";
import { createConversation, listConversations } from "@/lib/dummy/conversations";
import { DEFAULT_MODEL_ID } from "@/lib/dummy/models";

export async function GET() {
  return NextResponse.json({ conversations: listConversations() });
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const modelId = typeof body?.modelId === "string" ? body.modelId : DEFAULT_MODEL_ID;
  const conversation = createConversation(modelId);
  return NextResponse.json({ conversation }, { status: 201 });
}
