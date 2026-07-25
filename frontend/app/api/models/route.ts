import { NextResponse } from "next/server";
import type { ChatModel } from "@/lib/chat/models";

const MODEL_DETAILS: Record<
  string,
  Pick<ChatModel, "label" | "description">
> = {
  "gpt-4.1-mini": {
    label: "GPT-4.1 mini",
    description: "Fast, capable, and economical",
  },
  "gpt-5.6-terra": {
    label: "GPT-5.6 Terra",
    description: "Balanced intelligence and cost",
  },
  "gpt-5.6-luna": {
    label: "GPT-5.6 Luna",
    description: "Efficient for high-volume workloads",
  },
};

export async function GET() {
  const defaultModel =
    process.env.CHAT_MODEL_ID?.trim() || "gpt-4.1-mini";
  const configuredModels = (
    process.env.CHAT_MODEL_IDS ||
    "gpt-4.1-mini,gpt-5.6-terra,gpt-5.6-luna"
  )
    .split(",")
    .map((model) => model.trim())
    .filter(Boolean);
  const modelIds = Array.from(new Set([defaultModel, ...configuredModels]));
  const models: ChatModel[] = modelIds.map((id) => ({
    id,
    label: MODEL_DETAILS[id]?.label ?? id,
    provider: "OPENAI",
    description:
      MODEL_DETAILS[id]?.description ?? "Configured OpenAI API model",
  }));
  return NextResponse.json({ models });
}
