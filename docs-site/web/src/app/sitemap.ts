import type { MetadataRoute } from "next";
import { getGuides } from "@/lib/guides";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const guides = await getGuides();
  const baseUrl =
    process.env.DOCS_SITE_URL ?? "https://docs-chargepilot.endusercompute.in";

  return [
    { url: baseUrl, changeFrequency: "weekly", priority: 1 },
    ...guides.map((guide) => ({
      url: `${baseUrl}/guides/${guide.slug}`,
      lastModified: guide.updatedAt,
      changeFrequency: "monthly" as const,
      priority: guide.section === "Release notes" ? 0.5 : 0.8,
    })),
  ];
}
