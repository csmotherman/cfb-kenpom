"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

function safeNext(value: FormDataEntryValue | string | null | undefined) {
  const next = String(value ?? "").trim();
  return next.startsWith("/") && !next.startsWith("//") ? next : "/account";
}

function withMessage(
  path: string,
  key: "error" | "message",
  message: string,
  next?: string
) {
  const params = new URLSearchParams({ [key]: message });
  const safe = next ? safeNext(next) : "/account";
  if (safe !== "/account") params.set("next", safe);
  return `${path}?${params.toString()}`;
}

async function requestOrigin() {
  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin");
  if (origin) return origin;

  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host");
  const protocol = requestHeaders.get("x-forwarded-proto") ?? "http";
  return host ? `${protocol}://${host}` : "http://localhost:3000";
}

export async function login(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  if (!email || !password) {
    redirect(withMessage("/login", "error", "Enter your email and password.", next));
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    redirect(withMessage("/login", "error", "Invalid email or password.", next));
  }

  revalidatePath("/", "layout");
  redirect(next);
}

export async function signup(formData: FormData) {
  const displayName = String(formData.get("display_name") ?? "").trim().slice(0, 80);
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  if (!email || password.length < 8) {
    redirect(
      withMessage(
        "/signup",
        "error",
        "Use a valid email and a password with at least 8 characters.",
        next
      )
    );
  }

  const supabase = await createClient();
  const origin = await requestOrigin();
  const callbackUrl = new URL("/auth/callback", origin);
  callbackUrl.searchParams.set("next", next);

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { display_name: displayName || null },
      emailRedirectTo: callbackUrl.toString(),
    },
  });

  if (error) {
    redirect(
      withMessage(
        "/signup",
        "error",
        "We couldn't create that account. Check your email and password and try again.",
        next
      )
    );
  }

  revalidatePath("/", "layout");

  if (data.session) {
    redirect(next);
  }

  redirect(
    withMessage(
      "/login",
      "message",
      "Check your email to confirm your LEILA Ratings account, then sign in.",
      next
    )
  );
}

export async function updateDisplayName(formData: FormData) {
  const displayName = String(formData.get("display_name") ?? "").trim().slice(0, 80);
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const userId = claimsData?.claims?.sub;

  if (!userId) {
    redirect(withMessage("/login", "message", "Sign in to manage your LEILA Ratings account."));
  }

  const { error } = await supabase
    .from("profiles")
    .update({ display_name: displayName || null })
    .eq("id", userId);

  if (error) {
    redirect(withMessage("/account", "error", "Your account name could not be updated."));
  }

  revalidatePath("/account");
  redirect(withMessage("/account", "message", "Account updated."));
}
