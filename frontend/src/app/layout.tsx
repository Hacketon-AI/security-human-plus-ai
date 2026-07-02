import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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

export const metadata: Metadata = {
  title: "SecureScope — Authorized Security Validation Control",
  description:
    "SecureScope is a security validation execution and penetration validation orchestration platform for security operators, pentest coordinators, auditors, and administrators.",
  keywords: [
    "SecureScope",
    "penetration testing",
    "security validation",
    "SOC",
    "offensive security orchestration",
  ],
  authors: [{ name: "SecureScope" }],
  icons: { icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground min-h-screen`}
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
