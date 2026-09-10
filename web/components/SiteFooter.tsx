import Link from "next/link";

export default function SiteFooter({ note }: { note: string }) {
  const brandedNote = note
    .replaceAll("CollegeFootballFocus", "LEILA Ratings")
    .replaceAll("College Football Focus", "LEILA Ratings")
    .replaceAll("ARA Advanced Analytics", "LEILA Pro")
    .replaceAll("Advanced CFF", "LEILA Pro")
    .replaceAll("Advanced ARA", "LEILA Pro")
    .replaceAll("AdjNet", "Adj. Net")
    .replaceAll("AdjEM", "Adj. Net")
    .replaceAll("AdjOff", "Adj. Off")
    .replaceAll(/AdjO(?!ff)/g, "Adj. Off")
    .replaceAll("AdjDef", "Adj. Def")
    .replaceAll(/AdjD(?!ef)/g, "Adj. Def")
    .replaceAll("CFF", "LEILA Ratings");

  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <div className="site-footer__copy">
          <strong className="site-footer__brand">LEILA Ratings</strong>
          <p>{brandedNote}</p>
        </div>
        <div className="site-footer__links">
          <Link href="/methodology">Methodology</Link>
          <Link href="/predictions">Predictions</Link>
          <Link href="/upgrade">LEILA Pro</Link>
        </div>
      </div>
    </footer>
  );
}
