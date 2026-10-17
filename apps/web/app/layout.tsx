import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Operion Evidence Desk",
  description: "Read-only customer and fulfillment evidence",
};

export const dynamic = "force-dynamic";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-dvh">
      <body className="h-dvh font-sans">
        {children}
      </body>
    </html>
  );
}
