import Link from "next/link";

export default function SiteFooter({ note }: { note: string }) {
  const brandedNote = note
    .replaceAll("CollegeFootballFocus", "PRIME Football")
    .replaceAll("College Football Focus", "PRIME Football")
    .replaceAll("ARA Advanced Analytics", "PRIME Advanced")
    .replaceAll("Advanced CFF", "PRIME Advanced")
    .replaceAll("Advanced ARA", "PRIME Advanced")
    .replaceAll("AdjNet", "Adj. Net")
    .replaceAll("AdjEM", "Adj. Net")
    .replaceAll("AdjOff", "Adj. Off")
    .replaceAll(/AdjO(?!ff)/g, "Adj. Off")
    .replaceAll("AdjDef", "Adj. Def")
    .replaceAll(/AdjD(?!ef)/g, "Adj. Def")
    .replaceAll("CFF", "PRIME Football");

  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <div className="site-footer__copy">
          <strong className="site-footer__brand">PRIME Football</strong>
          <p>{brandedNote}</p>
        </div>
        <div className="site-footer__links">
          <Link href="/methodology">Methodology</Link>
          <Link href="/predictions">Predictions</Link>
          <Link href="/upgrade">PRIME Advanced</Link>
        </div>
      </div>
    </footer>
  );
}
