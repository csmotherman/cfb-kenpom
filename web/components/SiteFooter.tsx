import Link from "next/link";

export default function SiteFooter({ note }: { note: string }) {
  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <p>{note}</p>
        <div className="site-footer__links">
          <Link href="/advanced">Advanced CFF</Link>
          <Link href="/predictions">Predictions</Link>
        </div>
      </div>
    </footer>
  );
}
