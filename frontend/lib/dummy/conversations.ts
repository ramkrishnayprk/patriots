// In-memory mock of the Conversation/Message tables in prisma/schema.prisma.
// Resets on server restart — good enough for a UI-only pass; the shape is
// deliberately close to the real models so swapping this module for actual
// Prisma calls later is mostly a search-and-replace.

export interface ChatSource {
  chunkId: string;
  title: string;
  url: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  sources?: ChatSource[];
}

export interface Conversation {
  id: string;
  title: string;
  modelId: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

function seedConversations(): Conversation[] {
  const now = new Date();
  const hoursAgo = (h: number) => new Date(now.getTime() - h * 3600_000).toISOString();

  return [
    {
      id: "conv-1",
      title: "Oppenheimer cast & director",
      modelId: "gpt-5.2",
      createdAt: hoursAgo(2),
      updatedAt: hoursAgo(2),
      messages: [
        {
          id: "msg-1a",
          role: "user",
          content: "Who directed Oppenheimer and who stars in it?",
          createdAt: hoursAgo(2),
        },
        {
          id: "msg-1b",
          role: "assistant",
          content:
            "Oppenheimer (2023) was directed by Christopher Nolan. It stars Cillian Murphy as J. Robert Oppenheimer, alongside Emily Blunt, Matt Damon, and Robert Downey Jr. The film runs 180 minutes and was shot largely on IMAX 65mm film.",
          createdAt: hoursAgo(2),
          sources: [
            { chunkId: "tmdb-872585-crew", title: "Oppenheimer (2023) — Cast & Crew", url: "https://www.themoviedb.org/movie/872585-oppenheimer" },
          ],
        },
      ],
    },
    {
      id: "conv-2",
      title: "Breaking Bad finale rating",
      modelId: "gpt-5.2",
      createdAt: hoursAgo(26),
      updatedAt: hoursAgo(25),
      messages: [
        {
          id: "msg-2a",
          role: "user",
          content: "What's the IMDb rating for Breaking Bad's series finale?",
          createdAt: hoursAgo(26),
        },
        {
          id: "msg-2b",
          role: "assistant",
          content:
            "\"Felina\" (S5E16), Breaking Bad's series finale, holds a 9.9/10 rating on IMDb — one of the highest-rated finales of any TV series. The show overall averages 9.5/10 across all five seasons.",
          createdAt: hoursAgo(25),
          sources: [
            { chunkId: "imdb-tt2301451-rating", title: "Breaking Bad — Felina (S5E16)", url: "https://www.imdb.com/title/tt2301451/" },
          ],
        },
      ],
    },
    {
      id: "conv-3",
      title: "Dune: Part Two box office",
      modelId: "claude-sonnet-5",
      createdAt: hoursAgo(72),
      updatedAt: hoursAgo(70),
      messages: [
        {
          id: "msg-3a",
          role: "user",
          content: "How much did Dune: Part Two make at the box office?",
          createdAt: hoursAgo(72),
        },
        {
          id: "msg-3b",
          role: "assistant",
          content:
            "Dune: Part Two (2024) grossed roughly $714 million worldwide against a production budget of about $190 million, making it one of the most profitable releases of 2024.",
          createdAt: hoursAgo(70),
          sources: [
            { chunkId: "tmdb-693134-financials", title: "Dune: Part Two (2024) — Financials", url: "https://www.themoviedb.org/movie/693134-dune-part-two" },
          ],
        },
      ],
    },
    {
      id: "conv-4",
      title: "Barbie release date & genre",
      modelId: "gpt-5.2-mini",
      createdAt: hoursAgo(150),
      updatedAt: hoursAgo(150),
      messages: [
        {
          id: "msg-4a",
          role: "user",
          content: "When did Barbie (2023) release and what genre is it?",
          createdAt: hoursAgo(150),
        },
        {
          id: "msg-4b",
          role: "assistant",
          content:
            "Barbie (2023) released in theaters on July 21, 2023. It's a comedy-fantasy directed by Greta Gerwig, starring Margot Robbie and Ryan Gosling.",
          createdAt: hoursAgo(150),
          sources: [
            { chunkId: "tmdb-346698-overview", title: "Barbie (2023) — Overview", url: "https://www.themoviedb.org/movie/346698-barbie" },
          ],
        },
      ],
    },
  ];
}

let conversations: Conversation[] = seedConversations();

export function listConversations(): Conversation[] {
  return [...conversations].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}

export function getConversation(id: string): Conversation | undefined {
  return conversations.find((c) => c.id === id);
}

export function createConversation(modelId: string): Conversation {
  const now = new Date().toISOString();
  const conv: Conversation = {
    id: `conv-${Date.now()}`,
    title: "New chat",
    modelId,
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
  conversations = [conv, ...conversations];
  return conv;
}

export function renameConversation(id: string, title: string): Conversation | undefined {
  const conv = getConversation(id);
  if (!conv) return undefined;
  conv.title = title.trim() || conv.title;
  conv.updatedAt = new Date().toISOString();
  return conv;
}

export function deleteConversation(id: string): boolean {
  const before = conversations.length;
  conversations = conversations.filter((c) => c.id !== id);
  return conversations.length < before;
}

export function appendMessage(conversationId: string, message: ChatMessage): Conversation | undefined {
  const conv = getConversation(conversationId);
  if (!conv) return undefined;
  conv.messages.push(message);
  conv.updatedAt = message.createdAt;
  if (conv.messages.length === 1 && message.role === "user") {
    conv.title = message.content.slice(0, 60);
  }
  return conv;
}
