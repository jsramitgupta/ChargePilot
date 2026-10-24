import Link from "next/link";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SiteShell } from "@/components/SiteShell";
import { getGuide, getGuides } from "@/lib/guides";

export const dynamic = "force-dynamic";

type GuidePageProps = {
  params: Promise<{ slug: string }>;
};

export default async function GuidePage({ params }: GuidePageProps) {
  const { slug } = await params;
  const [guide, guides] = await Promise.all([getGuide(slug), getGuides()]);

  if (!guide) {
    notFound();
  }

  return (
    <SiteShell guides={guides} activeSlug={guide.slug}>
      <main id="main-content" className="article-content">
        <article>
          <header className="article-heading">
            <Link className="back-link" href="/">
              All help topics
            </Link>
            <p className="article-section">{guide.section}</p>
            <h1>{guide.title}</h1>
            <p className="article-summary">{guide.summary}</p>
            <div className="article-meta">
              <span>{audienceLabel(guide.audience)}</span>
              <span>{guide.readingMinutes} min read</span>
            </div>
          </header>
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {guide.body}
            </ReactMarkdown>
          </div>
        </article>
      </main>
    </SiteShell>
  );
}

function audienceLabel(audience: "all" | "tenant_admin" | "user") {
  if (audience === "tenant_admin") {
    return "Tenant admins and managers";
  }
  return audience === "user" ? "Users" : "Everyone";
}
