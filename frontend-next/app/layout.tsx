import type { Metadata } from "next";
import Link from "next/link";

import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Car Crash AI",
  description: "Photograph a damaged car and get a parts-and-labour repair estimate.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="sheet">
          <header className="masthead">
            <Link href="/" className="masthead__name">
              Car Crash AI
            </Link>
            <Nav />
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
