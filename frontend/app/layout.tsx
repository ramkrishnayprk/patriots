import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UC Degree Scraper",
  description: "University degree scraping workspace",
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
