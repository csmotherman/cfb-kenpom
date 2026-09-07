"use client";

import Link from "next/link";

export default function DataError() {
  return (
    <main className="container loading-state" role="alert">
      <h1>We couldn’t load this page</h1>
      <p>Please check your connection and try again. Published ratings are preserved while data is unavailable.</p>
      <button type="button" onClick={() => window.location.reload()}>Reload page</button>
      <Link href="/">Back to ratings</Link>
    </main>
  );
}
