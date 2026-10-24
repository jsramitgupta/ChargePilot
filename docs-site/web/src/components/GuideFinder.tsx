"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { GuideSummary } from "@/lib/guides";

type AudienceFilter = "all" | "tenant_admin" | "user";

const filters: { value: AudienceFilter; label: string }[] = [
  { value: "all", label: "All topics" },
  { value: "tenant_admin", label: "Tenant admins" },
  { value: "user", label: "Users" },
];

export function GuideFinder({ guides }: { guides: GuideSummary[] }) {
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState<AudienceFilter>("all");
  const filteredGuides = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return guides.filter((guide) => {
      const audienceMatches =
        audience === "all" ||
        guide.audience === audience ||
        guide.audience === "all";
      const textMatches =
        normalizedQuery.length === 0 ||
        `${guide.title} ${guide.summary} ${guide.section}`
          .toLocaleLowerCase()
          .includes(normalizedQuery);
      return audienceMatches && textMatches;
    });
  }, [audience, guides, query]);

  return (
    <section className="topic-finder" aria-labelledby="topic-finder-heading">
      <div className="finder-heading">
        <div>
          <p className="eyebrow">Find a task</p>
          <h2 id="topic-finder-heading">What are you trying to do?</h2>
        </div>
        <label className="search-field">
          <span>Search help topics</span>
          <input
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="For example, invite a teammate"
            type="search"
            value={query}
          />
        </label>
      </div>
      <div className="filter-row" role="group" aria-label="Filter by audience">
        {filters.map((filter) => (
          <button
            aria-pressed={audience === filter.value}
            className={audience === filter.value ? "filter-active" : ""}
            key={filter.value}
            onClick={() => setAudience(filter.value)}
            type="button"
          >
            {filter.label}
          </button>
        ))}
      </div>
      {filteredGuides.length > 0 ? (
        <ul className="topic-list" aria-live="polite">
          {filteredGuides.map((guide) => (
            <li key={guide.slug}>
              <Link href={`/guides/${guide.slug}`}>
                <span className="topic-copy">
                  <strong>{guide.title}</strong>
                  <span>{guide.summary}</span>
                </span>
                <span className="topic-meta">
                  {guide.section} · {guide.readingMinutes} min
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-search" role="status">
          No topics match that search. Try a different word or clear the
          audience filter.
        </p>
      )}
    </section>
  );
}
