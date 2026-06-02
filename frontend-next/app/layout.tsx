import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Car Crash AI",
  description: "AI-powered vehicle damage assessment and cost estimation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="bg-brand shadow-sm">
          <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
            <h1 className="text-white font-bold text-lg tracking-tight">Car Crash AI</h1>
            <a href="/history" className="text-blue-200 hover:text-white text-sm transition-colors">
              Estimate History
            </a>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
