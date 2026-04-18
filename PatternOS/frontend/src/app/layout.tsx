import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Shell } from "@/components/shell";
import { Toaster } from "@/components/ui/sonner";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PatternOS",
  description: "AI-powered chart pattern signal intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-background text-foreground`}>
        <Shell>{children}</Shell>
        <Toaster />
      </body>
    </html>
  );
}
