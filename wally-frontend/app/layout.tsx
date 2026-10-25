import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";
import localFont from "next/font/local";
import { ToastProvider } from "@/components/Toaster";
import "./globals.css";

const figtree = Figtree({
  variable: "--font-figtree",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const satoshi = localFont({
  variable: "--font-satoshi",
  src: [
    { path: "./fonts/Satoshi-300.woff2", weight: "300" },
    { path: "./fonts/Satoshi-400.woff2", weight: "400" },
    { path: "./fonts/Satoshi-500.woff2", weight: "500" },
    { path: "./fonts/Satoshi-700.woff2", weight: "700" },
    { path: "./fonts/Satoshi-900.woff2", weight: "900" },
  ],
});

export const viewport: Viewport = {
  colorScheme: "only light",
  themeColor: "#f5f5f5",
};

export const metadata: Metadata = {
  title: "Wally",
  description: "Grounded, cited answers from your company's documents.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${figtree.variable} ${satoshi.variable} h-full`}>
      <body className="min-h-full font-sans text-[15px] leading-normal">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
