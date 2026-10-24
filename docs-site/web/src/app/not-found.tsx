import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main-content" className="error-panel">
      <p className="eyebrow">Guide not found</p>
      <h1>This topic may have moved.</h1>
      <p>Browse the current help topics to find the right instructions.</p>
      <Link className="text-link" href="/">
        Browse help topics
      </Link>
    </main>
  );
}
