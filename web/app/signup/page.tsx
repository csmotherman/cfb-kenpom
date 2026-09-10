import type { Metadata } from "next";
import Link from "next/link";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import { signup } from "@/app/auth/actions";

export const metadata: Metadata = {
  title: "Create account | LEILA Ratings",
  robots: { index: false, follow: false },
};

type SignupPageProps = {
  searchParams: Promise<{ error?: string; next?: string }>;
};

function safeNext(value: string | undefined) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/account";
}

export default async function SignupPage({ searchParams }: SignupPageProps) {
  const params = await searchParams;
  const next = safeNext(params.next);
  const returningToUpgrade = next.startsWith("/upgrade");

  return (
    <>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />
      <main className="auth-main">
        <div className="auth-shell">
          <section className="auth-panel" aria-labelledby="signupTitle">
            <span className="eyebrow auth-kicker">LEILA Ratings Account</span>
            <h1 id="signupTitle" className="auth-title">Create account</h1>
            <p className="auth-copy">
              {returningToUpgrade
                ? "Create your LEILA Ratings account with just email and password. After confirmation, we'll bring you back to the plan you selected."
                : "Create a free LEILA Ratings account with just email and password. You can add profile details later."}
            </p>

            {params.error ? <p className="auth-alert auth-alert--error">{params.error}</p> : null}

            <form className="auth-form" action={signup}>
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
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
                <small className="auth-hint">8 characters minimum</small>
              </label>
              <button className="auth-button" type="submit">Create account</button>
            </form>

            <p className="auth-alt">
              Already have an account? <Link href={`/login?next=${encodeURIComponent(next)}`}>Sign in</Link>
            </p>
          </section>
        </div>
      </main>
      <SiteFooter note="LEILA Ratings accounts are free to create. Billing only starts if you later choose and confirm a paid subscription in Stripe Checkout." />
    </>
  );
}
