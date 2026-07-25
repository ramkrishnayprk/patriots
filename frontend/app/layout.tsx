import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Movie RAG",
  description: "IMDb and TMDb movie research workspace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
