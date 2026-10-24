import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: "/admin/",
    },
    sitemap: `${siteUrl()}/sitemap.xml`,
  };
}

function siteUrl() {
  return process.env.DOCS_SITE_URL ?? "https://docs-chargepilot.endusercompute.in";
}
