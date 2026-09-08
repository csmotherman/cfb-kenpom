import { redirect } from "next/navigation";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";

export const dynamic = "force-dynamic";

export default async function AdvancedLayout({ children }: { children: React.ReactNode }) {
  const entitlements = await getCurrentEntitlements();

  if (!entitlements.advanced) {
    redirect("/upgrade?feature=advanced");
  }

  return children;
}
