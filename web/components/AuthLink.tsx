"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function AuthLink() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let mounted = true;
    const supabase = createClient();

    supabase.auth.getClaims().then(({ data }) => {
      if (mounted) setSignedIn(Boolean(data?.claims));
    }).catch(() => {
      if (mounted) setSignedIn(false);
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (mounted) setSignedIn(Boolean(session));
    });

    return () => {
      mounted = false;
      data.subscription.unsubscribe();
    };
  }, []);

  return (
    <Link className="auth-link" href={signedIn ? "/account" : "/login"}>
      <svg className="auth-link__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="12" cy="8" r="3.25" />
        <path d="M5.5 19c.7-3.4 3-5.25 6.5-5.25s5.8 1.85 6.5 5.25" />
      </svg>
      <span>{signedIn ? "Account" : "Sign in"}</span>
    </Link>
  );
}
