import type { Metadata } from "next";
import Link from "next/link";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import { signup } from "@/app/auth/actions";

export const metadata: Metadata = {
  title: "Create account | GRID",
  robots: { index: false, follow: false },
};

type SignupPageProps = {
  searchParams: Promise<{ error?: string }>;
};

export default async function SignupPage({ searchParams }: SignupPageProps) {
  const params = await searchParams;

  return (
    <>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />
      <main className="auth-main">
        <div className="auth-shell">
          <section className="auth-panel" aria-labelledby="signupTitle">
            <span className="eyebrow auth-kicker">GRID Account</span>
            <h1 id="signupTitle" className="auth-title">Create account</h1>
            <p className="auth-copy">
              Create your account now. Billing is not enabled yet, so signing up does not start a paid plan.
            </p>

            {params.error ? <p className="auth-alert auth-alert--error">{params.error}</p> : null}

            <form className="auth-form" action={signup}>
              <label className="auth-field">
                <span>Name <small>optional</small></span>
                <input
                  name="display_name"
                  type="text"
                  autoComplete="name"
                  maxLength={80}
                />
              </label>
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
              Already have an account? <Link href="/login">Sign in</Link>
            </p>
          </section>
        </div>
      </main>
      <SiteFooter note="GRID accounts are free to create. Paid GRID Pro and GRID Pro+ subscriptions will be handled separately through billing." />
    </>
  );
}
