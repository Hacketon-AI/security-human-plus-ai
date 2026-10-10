import type { Metadata } from "next";
import { Geist, Geist_Mono, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "SecureScope — Authorized Security Validation Control",
  description:
    "SecureScope verifies asset ownership, enforces written authorization, and runs safe, scope-locked security validation with human-reviewed, AI-assisted proof-of-risk.",
  keywords: [
    "SecureScope",
    "authorized security testing",
    "security validation",
    "proof-of-risk",
    "penetration testing",
  ],
  authors: [{ name: "SecureScope" }],
  icons: { icon: "/securescope-favicon.png" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${jetbrains.variable} antialiased bg-background text-foreground min-h-screen`}
      >
        {children}
        <Toaster />
        <SonnerToaster
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: "#0E1626",
              border: "1px solid #1E2A40",
              color: "#E2E8F0",
            },
          }}
        />
      </body>
    </html>
  );
}
