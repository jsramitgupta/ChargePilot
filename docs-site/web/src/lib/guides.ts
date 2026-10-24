export type GuideSummary = {
  title: string;
  slug: string;
  summary: string;
  audience: "all" | "tenant_admin" | "user";
  section: string;
  sortOrder: number;
  readingMinutes: number;
  updatedAt: string;
};

export type Guide = GuideSummary & { body: string };

export async function getGuides(): Promise<GuideSummary[]> {
  const response = await fetch(apiUrl(), { next: { revalidate: 60 } });
  if (!response.ok) {
    throw new Error(
      `The documentation CMS returned HTTP ${response.status}.`,
    );
  }

  const payload: unknown = await response.json();
  if (!isRecord(payload) || !Array.isArray(payload.data)) {
    throw new Error("The documentation CMS returned an invalid guide list.");
  }

  return payload.data
    .map(parseGuideSummary)
    .sort((first, second) => first.sortOrder - second.sortOrder);
}

export async function getGuide(slug: string): Promise<Guide | undefined> {
  const response = await fetch(
    `${apiUrl()}/${encodeURIComponent(slug)}`,
    { next: { revalidate: 60 } },
  );
  if (response.status === 404) {
    return undefined;
  }
  if (!response.ok) {
    throw new Error(
      `The documentation CMS returned HTTP ${response.status}.`,
    );
  }

  const payload: unknown = await response.json();
  if (!isRecord(payload) || payload.data === null) {
    return undefined;
  }
  if (!isRecord(payload.data)) {
    throw new Error("The documentation CMS returned an invalid guide.");
  }

  const summary = parseGuideSummary(payload.data);
  const body = payload.data.body;
  if (typeof body !== "string") {
    throw new Error("The documentation CMS returned a guide without content.");
  }
  return { ...summary, body };
}

function parseGuideSummary(value: unknown): GuideSummary {
  if (!isRecord(value)) {
    throw new Error("The documentation CMS returned an invalid guide entry.");
  }

  const {
    title,
    slug,
    summary,
    audience,
    section,
    sortOrder,
    readingMinutes,
    updatedAt,
  } = value;
  if (
    typeof title !== "string" ||
    typeof slug !== "string" ||
    typeof summary !== "string" ||
    !isAudience(audience) ||
    typeof section !== "string" ||
    typeof sortOrder !== "number" ||
    typeof readingMinutes !== "number" ||
    typeof updatedAt !== "string"
  ) {
    throw new Error("The documentation CMS returned an invalid guide entry.");
  }
  return {
    title,
    slug,
    summary,
    audience,
    section,
    sortOrder,
    readingMinutes,
    updatedAt,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isAudience(value: unknown): value is GuideSummary["audience"] {
  return value === "all" || value === "tenant_admin" || value === "user";
}

function apiUrl() {
  return (
    process.env.CMS_API_URL ??
    "http://localhost:1337/api/public/guides"
  ).replace(/\/$/, "");
}
