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
      {signedIn ? "Account" : "Sign in"}
    </Link>
  );
}
