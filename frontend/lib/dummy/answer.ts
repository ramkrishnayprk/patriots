import type { ChatSource } from "./conversations";

interface CannedAnswer {
  keywords: string[];
  text: string;
  sources: ChatSource[];
}

// Placeholder for lib/retrieval.ts + a provider adapter — keyword-matched
// canned answers instead of a real hybrid search + LLM call.
const CANNED_ANSWERS: CannedAnswer[] = [
  {
    keywords: ["director", "directed", "crew"],
    text: "Oppenheimer (2023) was directed by Christopher Nolan, who also wrote the screenplay based on the biography American Prometheus. It's his first film shot entirely in a mix of IMAX 65mm and 65mm large-format film, including black-and-white sequences.",
    sources: [{ chunkId: "tmdb-872585-crew", title: "Oppenheimer (2023) — Cast & Crew", url: "https://www.themoviedb.org/movie/872585-oppenheimer" }],
  },
  {
    keywords: ["cast", "starring", "actor", "actress"],
    text: "Dune: Part Two (2024) stars Timothée Chalamet as Paul Atreides, Zendaya as Chani, Rebecca Ferguson as Lady Jessica, and Javier Bardem as Stilgar, with Austin Butler joining as Feyd-Rautha.",
    sources: [{ chunkId: "tmdb-693134-cast", title: "Dune: Part Two (2024) — Cast", url: "https://www.themoviedb.org/movie/693134-dune-part-two" }],
  },
  {
    keywords: ["rating", "score", "imdb rating"],
    text: "Breaking Bad holds a 9.5/10 average rating on IMDb across its five seasons — one of the highest-rated TV series ever tracked. The series finale, \"Felina\" (S5E16), is individually rated 9.9/10.",
    sources: [{ chunkId: "imdb-tt0903747-rating", title: "Breaking Bad — IMDb Ratings", url: "https://www.imdb.com/title/tt0903747/" }],
  },
  {
    keywords: ["budget", "box office", "revenue", "gross"],
    text: "Barbie (2023) was made on a reported budget of around $145 million and grossed over $1.44 billion worldwide, making it the highest-grossing film of 2023 and Warner Bros.' highest-grossing release of all time.",
    sources: [{ chunkId: "tmdb-346698-financials", title: "Barbie (2023) — Box Office", url: "https://www.themoviedb.org/movie/346698-barbie" }],
  },
  {
    keywords: ["release date", "when did", "genre", "similar"],
    text: "Poor Things (2023) is a sci-fi comedy-drama directed by Yorgos Lanthimos, released in U.S. theaters on December 8, 2023. Fans of its surreal tone often also enjoy The Lobster and The Favourite, both from the same director.",
    sources: [{ chunkId: "tmdb-792307-overview", title: "Poor Things (2023) — Overview", url: "https://www.themoviedb.org/movie/792307-poor-things" }],
  },
];

const FALLBACK_ANSWER: CannedAnswer = {
  keywords: [],
  text: "I don't have a specific answer for that in the sample data yet, but once this is wired to the real retrieval pipeline it'll search indexed TMDB and IMDb data and cite the exact title pages it used.",
  sources: [],
};

export function pickAnswer(userText: string): CannedAnswer {
  const lower = userText.toLowerCase();
  return CANNED_ANSWERS.find((a) => a.keywords.some((k) => lower.includes(k))) ?? FALLBACK_ANSWER;
}
