import Link from "next/link";
import type { GuideSummary } from "@/lib/guides";

export function SiteShell({
  guides,
  activeSlug,
  children,
}: {
  guides: GuideSummary[];
  activeSlug?: string;
  children: React.ReactNode;
}) {
  const sections = groupSections(guides);

  return (
    <div className="site-frame">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <Link className="brand" href="/" aria-label="ChargePilot help home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            <strong>ChargePilot</strong>
            <small>Help for your workspace</small>
          </span>
        </Link>
        <nav className="header-actions" aria-label="Account links">
          <Link href="https://console-chargepilot.endusercompute.in/login">
            Open ChargePilot
          </Link>
        </nav>
      </header>
      <div className="page-frame">
        <aside className="topic-rail" aria-label="Help topics">
          <p className="rail-heading">Topics</p>
          {sections.map(([section, items]) => (
            <section className="rail-section" key={section}>
              <h2>{section}</h2>
              <ul>
                {items.map((guide) => (
                  <li key={guide.slug}>
                    <Link
                      aria-current={
                        guide.slug === activeSlug ? "page" : undefined
                      }
                      className={
                        guide.slug === activeSlug ? "active-topic" : undefined
                      }
                      href={`/guides/${guide.slug}`}
                    >
                      {guide.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <p className="rail-footer">
            Need help with your account?{" "}
            <Link href="https://console-chargepilot.endusercompute.in/support">
              Contact support
            </Link>
          </p>
        </aside>
        {children}
      </div>
      <footer className="site-footer">
        <span>ChargePilot documentation</span>
        <span>Battery rules stay on the ChargePilot server.</span>
      </footer>
    </div>
  );
}

function groupSections(guides: GuideSummary[]) {
  const groups = new Map<string, GuideSummary[]>();
  for (const guide of guides) {
    const section = groups.get(guide.section) ?? [];
    section.push(guide);
    groups.set(guide.section, section);
  }
  return [...groups.entries()];
}
