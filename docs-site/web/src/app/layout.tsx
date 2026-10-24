import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ChargePilot help",
    template: "%s | ChargePilot help",
  },
  description:
    "Task-based guides for ChargePilot tenant administrators and users.",
  metadataBase: new URL(
    process.env.DOCS_SITE_URL ??
      "https://docs-chargepilot.endusercompute.in",
  ),
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
