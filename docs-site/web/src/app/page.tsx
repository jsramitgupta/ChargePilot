import Link from "next/link";
import { GuideFinder } from "@/components/GuideFinder";
import { SiteShell } from "@/components/SiteShell";
import { getGuides } from "@/lib/guides";

export const dynamic = "force-dynamic";

export default async function Home() {
  const guides = await getGuides();
  const latestRelease = guides.find((guide) => guide.section === "Release notes");

  return (
    <SiteShell guides={guides}>
      <main id="main-content" className="home-content">
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">ChargePilot help</p>
            <h1>Clear answers for the people and devices in your workspace.</h1>
            <p className="hero-summary">
              Set up your account, enroll battery-reporting devices, and
              understand how ChargePilot controls your switches.
            </p>
            <Link className="text-link" href="/guides/getting-started">
              Start with the basics
            </Link>
          </div>
          <div
            className="power-path"
            role="img"
            aria-label="Battery report flows through a ChargePilot rule and site connector to a local switch"
          >
            <div className="path-node battery-node">
              <span className="battery-icon" aria-hidden="true">
                <span />
              </span>
              <strong>Battery</strong>
              <small>fresh report</small>
            </div>
            <span className="path-line" aria-hidden="true" />
            <div className="path-node rule-node">
              <span className="rule-icon" aria-hidden="true">
                %
              </span>
              <strong>Rule</strong>
              <small>server decides</small>
            </div>
            <span className="path-line" aria-hidden="true" />
            <div className="path-node connector-node">
              <span className="connector-icon" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              <strong>Site connector</strong>
              <small>acts on the LAN</small>
            </div>
            <span className="path-line" aria-hidden="true" />
            <div className="path-node switch-node">
              <span className="switch-icon" aria-hidden="true">
                <i />
              </span>
              <strong>Switch</strong>
              <small>desired state</small>
            </div>
          </div>
        </section>

        {latestRelease && (
          <section className="release-note" aria-labelledby="release-heading">
            <div>
              <p className="eyebrow">Latest release</p>
              <h2 id="release-heading">{latestRelease.title}</h2>
              <p>{latestRelease.summary}</p>
            </div>
            <Link
              className="text-link"
              href={`/guides/${latestRelease.slug}`}
            >
              Read what changed
            </Link>
          </section>
        )}

        <GuideFinder guides={guides} />
      </main>
    </SiteShell>
  );
}
