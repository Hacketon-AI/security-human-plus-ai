import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "Double AA · Authorized security validation",
  description:
    "Double AA verifies asset ownership, enforces written authorization, and runs safe, scope-locked security validation with human-reviewed, AI-assisted proof-of-risk.",
  keywords: [
    "Double AA",
    "authorized security testing",
    "security validation",
    "proof-of-risk",
    "penetration testing",
  ],
  authors: [{ name: "Double AA" }],
  icons: { icon: "/doubleaa-mark.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`dark ${plexSans.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <body
        className={`antialiased bg-background text-foreground min-h-screen`}
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
