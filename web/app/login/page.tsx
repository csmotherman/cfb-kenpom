import type { Metadata } from "next";
import Link from "next/link";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import { login } from "@/app/auth/actions";

export const metadata: Metadata = {
  title: "Sign in | GRID",
  robots: { index: false, follow: false },
};

type LoginPageProps = {
  searchParams: Promise<{ error?: string; message?: string; next?: string }>;
};

function safeNext(value: string | undefined) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/account";
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = safeNext(params.next);
  const returningToUpgrade = next.startsWith("/upgrade");

  return (
    <>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />
      <main className="auth-main">
        <div className="auth-shell">
          <section className="auth-panel" aria-labelledby="loginTitle">
            <span className="eyebrow auth-kicker">GRID Account</span>
            <h1 id="loginTitle" className="auth-title">Sign in</h1>
            <p className="auth-copy">
              {returningToUpgrade
                ? "Sign in and we'll bring you back to the GRID plan you selected."
                : "Sign in to manage your GRID account and paid access."}
            </p>

            {params.error ? <p className="auth-alert auth-alert--error">{params.error}</p> : null}
            {params.message ? <p className="auth-alert auth-alert--success">{params.message}</p> : null}

            <form className="auth-form" action={login}>
              <input type="hidden" name="next" value={next} />
              <label className="auth-field">
                <span>Email</span>
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  required
                />
              </label>
              <label className="auth-field">
                <span>Password</span>
                <input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </label>
              <button className="auth-button" type="submit">Sign in</button>
            </form>

            <p className="auth-alt">
              New to GRID? <Link href={`/signup?next=${encodeURIComponent(next)}`}>Create an account</Link>
            </p>
          </section>
        </div>
      </main>
      <SiteFooter note="GRID accounts power access to advanced analytics and prediction products. Ratings remain available without an account." />
    </>
  );
}
