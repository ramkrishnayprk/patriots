// Mirrors lib/providers (Provider enum: ANTHROPIC | OPENAI) so this list is a
// drop-in swap for a real "list available models" endpoint later.

export interface ChatModel {
  id: string;
  label: string;
  provider: "OPENAI" | "ANTHROPIC";
  description: string;
}

export const CHAT_MODELS: ChatModel[] = [
  {
    id: "gpt-5.2",
    label: "GPT-5.2",
    provider: "OPENAI",
    description: "Most capable — best for complex, multi-part questions",
  },
  {
    id: "gpt-5.2-mini",
    label: "GPT-5.2 Mini",
    provider: "OPENAI",
    description: "Faster and cheaper for everyday questions",
  },
  {
    id: "gpt-5.1-thinking",
    label: "GPT-5.1 Thinking",
    provider: "OPENAI",
    description: "Extended reasoning for tricky comparisons",
  },
  {
    id: "gpt-4o",
    label: "GPT-4o",
    provider: "OPENAI",
    description: "Balanced legacy model",
  },
  {
    id: "claude-sonnet-5",
    label: "Claude Sonnet 5",
    provider: "ANTHROPIC",
    description: "Anthropic's balanced flagship model",
  },
];

export const DEFAULT_MODEL_ID = CHAT_MODELS[0].id;
