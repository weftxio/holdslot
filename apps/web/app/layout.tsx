import type { Metadata } from "next";
import { Source_Serif_4, Archivo } from "next/font/google";
import "./globals.css";

// Display serif. Source Serif 4 reads cleaner than Fraunces (notably the "f");
// keep the --font-fraunces variable name so existing CSS consumers are unchanged.
const fraunces = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
  display: "swap",
});
const archivo = Archivo({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-archivo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "HoldSlot · Qualified meetings, booked for you",
  description: "Qualified sales meetings, booked for you.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${archivo.variable}`}>
      <body>{children}</body>
    </html>
  );
}
