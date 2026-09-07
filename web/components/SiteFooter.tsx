import Link from "next/link";

export default function SiteFooter({ note }: { note: string }) {
  const brandedNote = note
    .replaceAll("CollegeFootballFocus", "ARA")
    .replaceAll("Advanced CFF", "ARA Advanced Analytics")
    .replaceAll("CFF", "ARA");

  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <div className="site-footer__copy">
          <strong className="site-footer__brand">ARA</strong>
          <p>{brandedNote}</p>
        </div>
        <div className="site-footer__links">
          <Link href="/advanced">Advanced Analytics</Link>
          <Link href="/predictions">Predictions</Link>
        </div>
      </div>
    </footer>
  );
}
