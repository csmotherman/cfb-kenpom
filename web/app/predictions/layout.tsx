import { redirect } from "next/navigation";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";

export const dynamic = "force-dynamic";

export default async function PredictionsLayout({ children }: { children: React.ReactNode }) {
  const entitlements = await getCurrentEntitlements();

  if (entitlements.predictions === "none") {
    redirect("/upgrade?feature=predictions");
  }

  return children;
}
