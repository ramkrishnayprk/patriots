export interface AdminStats {
  totalConversations: number;
  totalMessages: number;
  totalDocuments: number;
  totalChunks: number;
  lastIngestAt: string;
  activeUsers7d: number;
}

export interface AdminDocument {
  id: string;
  title: string;
  category: string;
  url: string;
  chunkCount: number;
  lastCrawledAt: string;
  status: "indexed" | "pending" | "failed";
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: "admin" | "staff";
  lastActiveAt: string;
}

export function getAdminStats(): AdminStats {
  return {
    totalConversations: 128,
    totalMessages: 742,
    totalDocuments: 96,
    totalChunks: 1834,
    lastIngestAt: new Date(Date.now() - 6 * 3600_000).toISOString(),
    activeUsers7d: 37,
  };
}

export function getAdminDocuments(): AdminDocument[] {
  const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();
  return [
    { id: "doc-1", title: "Oppenheimer (2023)", category: "Drama", url: "https://www.themoviedb.org/movie/872585-oppenheimer", chunkCount: 28, lastCrawledAt: hoursAgo(6), status: "indexed" },
    { id: "doc-2", title: "Breaking Bad (2008–2013)", category: "Crime", url: "https://www.imdb.com/title/tt0903747/", chunkCount: 45, lastCrawledAt: hoursAgo(6), status: "indexed" },
    { id: "doc-3", title: "Dune: Part Two (2024)", category: "Sci-Fi", url: "https://www.themoviedb.org/movie/693134-dune-part-two", chunkCount: 33, lastCrawledAt: hoursAgo(6), status: "indexed" },
    { id: "doc-4", title: "Barbie (2023)", category: "Comedy", url: "https://www.themoviedb.org/movie/346698-barbie", chunkCount: 21, lastCrawledAt: hoursAgo(30), status: "indexed" },
    { id: "doc-5", title: "The Bear (2022–)", category: "Comedy-Drama", url: "https://www.imdb.com/title/tt14452776/", chunkCount: 18, lastCrawledAt: hoursAgo(30), status: "indexed" },
    { id: "doc-6", title: "Poor Things (2023)", category: "Fantasy", url: "https://www.themoviedb.org/movie/792307-poor-things", chunkCount: 22, lastCrawledAt: hoursAgo(54), status: "pending" },
    { id: "doc-7", title: "Furiosa: A Mad Max Saga (2024)", category: "Action", url: "https://www.themoviedb.org/movie/786892-furiosa-a-mad-max-saga", chunkCount: 0, lastCrawledAt: hoursAgo(90), status: "failed" },
  ];
}

export function getAdminUsers(): AdminUser[] {
  const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();
  return [
    { id: "user-1", name: "Maya Chen", email: "maya@cinebot.app", role: "admin", lastActiveAt: hoursAgo(1) },
    { id: "user-2", name: "Leo Marchetti", email: "leo@cinebot.app", role: "staff", lastActiveAt: hoursAgo(5) },
    { id: "user-3", name: "Ava Thompson", email: "ava@cinebot.app", role: "staff", lastActiveAt: hoursAgo(28) },
  ];
}
