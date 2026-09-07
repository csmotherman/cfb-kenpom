"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

function withMessage(path: string, key: "error" | "message", message: string) {
  return `${path}?${key}=${encodeURIComponent(message)}`;
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

  if (!email || !password) {
    redirect(withMessage("/login", "error", "Enter your email and password."));
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    redirect(withMessage("/login", "error", "Invalid email or password."));
  }

  revalidatePath("/", "layout");
  redirect("/account");
}

export async function signup(formData: FormData) {
  const displayName = String(formData.get("display_name") ?? "").trim().slice(0, 80);
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || password.length < 8) {
    redirect(
      withMessage(
        "/signup",
        "error",
        "Use a valid email and a password with at least 8 characters."
      )
    );
  }

  const supabase = await createClient();
  const origin = await requestOrigin();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { display_name: displayName || null },
      emailRedirectTo: `${origin}/auth/callback?next=/account`,
    },
  });

  if (error) {
    redirect(
      withMessage(
        "/signup",
        "error",
        "We couldn't create that account. Check your email and password and try again."
      )
    );
  }

  revalidatePath("/", "layout");

  if (data.session) {
    redirect("/account");
  }

  redirect(
    withMessage(
      "/login",
      "message",
      "Check your email to confirm your GRID account, then sign in."
    )
  );
}

export async function updateDisplayName(formData: FormData) {
  const displayName = String(formData.get("display_name") ?? "").trim().slice(0, 80);
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const userId = claimsData?.claims?.sub;

  if (!userId) {
    redirect(withMessage("/login", "message", "Sign in to manage your GRID account."));
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
