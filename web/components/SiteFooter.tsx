import Link from "next/link";

export default function SiteFooter({ note }: { note: string }) {
  const brandedNote = note
    .replaceAll("CollegeFootballFocus", "GRID")
    .replaceAll("College Football Focus", "GRID")
    .replaceAll("ARA Advanced Analytics", "GRID Pro")
    .replaceAll("Advanced CFF", "GRID Pro")
    .replaceAll("Advanced ARA", "GRID Pro")
    .replaceAll("AdjEM", "RPI")
    .replaceAll("AdjO", "RPI-O")
    .replaceAll("AdjD", "RPI-D")
    .replaceAll("CFF", "GRID");

  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <div className="site-footer__copy">
          <strong className="site-footer__brand">GRID</strong>
          <p>{brandedNote}</p>
        </div>
        <div className="site-footer__links">
          <Link href="/methodology">Methodology</Link>
          <Link href="/predictions">Predictions</Link>
          <Link href="/upgrade">GRID Pro</Link>
        </div>
      </div>
    </footer>
  );
}
