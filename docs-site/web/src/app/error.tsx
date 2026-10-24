"use client";

export default function SiteError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main id="main-content" className="error-panel" role="alert">
      <p className="eyebrow">Help is temporarily unavailable</p>
      <h1>We couldn’t load the ChargePilot guides.</h1>
      <p>
        The documentation service did not return its published content. Try
        again in a moment, or open the support page from ChargePilot.
      </p>
      <button className="button-link" onClick={reset} type="button">
        Try again
      </button>
    </main>
  );
}
