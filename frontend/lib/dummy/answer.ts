import type { ChatSource } from "./conversations";

interface CannedAnswer {
  keywords: string[];
  text: string;
  sources: ChatSource[];
}

// Placeholder for lib/retrieval.ts + a provider adapter — keyword-matched
// canned answers instead of a real hybrid search + LLM call. Answers are
// authored in markdown with bare [n] citation markers (not [n](url) links)
// — that's the same contract a real retrieval pipeline produces: the model
// cites by ordinal, the URL comes from retrieval, never from the model.
// See lib/markdown/remarkCitations.ts for how [n] becomes a clickable badge.
const CANNED_ANSWERS: CannedAnswer[] = [
  {
    keywords: ["director", "directed", "crew"],
    text: "## 🎬 Oppenheimer (2023) — Direction\n\n**Christopher Nolan** directed *Oppenheimer* and wrote the screenplay himself, adapting the Pulitzer-winning biography *American Prometheus*.[1]\n\n- 🎥 **Format** — the first feature shot on a mix of IMAX 65mm and 65mm large-format film, including custom black-and-white IMAX stock\n- ⏱️ **Runtime** — 180 minutes, Nolan's longest film\n- 🏆 **Academy Awards** — 7 wins, including Best Director and Best Picture[2]",
    sources: [
      { chunkId: "tmdb-872585-crew", title: "Oppenheimer (2023) — Cast & Crew", url: "https://www.themoviedb.org/movie/872585-oppenheimer" },
      { chunkId: "imdb-tt15398776-awards", title: "Oppenheimer — Awards", url: "https://www.imdb.com/title/tt15398776/awards/" },
    ],
  },
  {
    keywords: ["cast", "starring", "actor", "actress"],
    text: "## 🎭 Dune: Part Two (2024) — Principal Cast\n\n| Actor | Role |\n| --- | --- |\n| Timothée Chalamet | Paul Atreides |\n| Zendaya | Chani |\n| Rebecca Ferguson | Lady Jessica |\n| Javier Bardem | Stilgar |\n| Austin Butler | Feyd-Rautha |\n| Florence Pugh | Princess Irulan |\n\nButler and Pugh are the headline additions for the sequel.[1] **Denis Villeneuve** returns to direct, with Hans Zimmer again scoring.[2]",
    sources: [
      { chunkId: "tmdb-693134-cast", title: "Dune: Part Two (2024) — Cast", url: "https://www.themoviedb.org/movie/693134-dune-part-two" },
      { chunkId: "tmdb-693134-crew", title: "Dune: Part Two (2024) — Crew", url: "https://www.themoviedb.org/movie/693134-dune-part-two/cast" },
    ],
  },
  {
    keywords: ["rating", "score", "imdb rating"],
    text: "⭐ ***Breaking Bad*** averages **9.5/10** on IMDb across all five seasons — one of the highest-rated series ever tracked.[1]\n\n- 🥇 **\"Ozymandias\"** (S5E14) — **10/10**, the highest-rated episode of any series on IMDb\n- 🎬 **\"Felina\"** (S5E16) — **9.9/10**, the series finale\n- 📺 **62 episodes** over five seasons, 2008–2013\n\n> The final season holds a 99% critics score — a near-flawless landing for one of television's great tragedies.[2]",
    sources: [
      { chunkId: "imdb-tt0903747-ratings", title: "Breaking Bad — IMDb Ratings", url: "https://www.imdb.com/title/tt0903747/" },
      { chunkId: "rt-breaking-bad-s5", title: "Breaking Bad: Season 5 — Rotten Tomatoes", url: "https://www.rottentomatoes.com/tv/breaking_bad/s05" },
    ],
  },
  {
    keywords: ["budget", "box office", "revenue", "gross"],
    text: "## 💰 Barbie (2023) — Box Office\n\n- 💵 **Budget** — roughly $145 million[1]\n- 🌍 **Worldwide gross** — **$1.446 billion**[2]\n- 🇺🇸 **Domestic** — $636 million\n- 📅 **Released** — July 21, 2023\n\nThat made *Barbie* the **highest-grossing film of 2023** and Warner Bros.' biggest release of all time — helped considerably by the \"Barbenheimer\" double-feature it shared opening weekend with *Oppenheimer*.[3]",
    sources: [
      { chunkId: "tmdb-346698-financials", title: "Barbie (2023) — Box Office", url: "https://www.themoviedb.org/movie/346698-barbie" },
      { chunkId: "bom-tt1517268", title: "Barbie — Box Office Mojo", url: "https://www.boxofficemojo.com/title/tt1517268/" },
      { chunkId: "imdb-tt1517268-reception", title: "Barbie (2023) — Reception", url: "https://www.imdb.com/title/tt1517268/" },
    ],
  },
  {
    keywords: ["release date", "when did", "genre", "similar"],
    text: "📅 ***Poor Things*** (2023) opened in U.S. theaters on **December 8, 2023** — a sci-fi comedy-drama from **Yorgos Lanthimos**, starring Emma Stone as Bella Baxter in an Oscar-winning turn.[1]\n\nIf the surreal streak is what you're after, *The Favourite* (2018) and *The Lobster* (2015) are the same director on the same wavelength.[2]",
    sources: [
      { chunkId: "tmdb-792307-overview", title: "Poor Things (2023) — Overview", url: "https://www.themoviedb.org/movie/792307-poor-things" },
      { chunkId: "tmdb-person-4429", title: "Yorgos Lanthimos — Filmography", url: "https://www.themoviedb.org/person/4429-yorgos-lanthimos" },
    ],
  },
];

const FALLBACK_ANSWER: CannedAnswer = {
  keywords: [],
  text: "🍿 I don't have that one in the sample index yet.\n\nOnce this is wired to the real retrieval pipeline it'll search indexed TMDB and IMDb chunks and cite the exact title pages it used. In the meantime, try:\n\n- 🎬 *\"Who directed Oppenheimer?\"*\n- 🎭 *\"Who stars in Dune: Part Two?\"*\n- ⭐ *\"What's Breaking Bad rated on IMDb?\"*\n- 💰 *\"How much did Barbie gross worldwide?\"*",
  sources: [],
};

export function pickAnswer(userText: string): CannedAnswer {
  const lower = userText.toLowerCase();
  return CANNED_ANSWERS.find((a) => a.keywords.some((k) => lower.includes(k))) ?? FALLBACK_ANSWER;
}
