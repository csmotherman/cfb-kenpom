import { notFound, permanentRedirect } from "next/navigation";
import { getLatestYear, getScheduleServer } from "@/lib/seoData";

type Params = { params: Promise<{ week: string }> };

export const dynamicParams = false;

export async function generateStaticParams() {
  const year = await getLatestYear();
  const schedule = year ? await getScheduleServer(year) : null;
  return (schedule?.weeks ?? []).map((week) => ({ week: String(week) }));
}

/**
 * Legacy week hub URL.
 *
 * Week browsing belongs inside the Predictions product. Keep these URLs as
 * permanent redirects so old links/bookmarks continue working without
 * exposing a second, differently styled weekly experience.
 */
export default async function WeekRedirect({ params }: Params) {
  const raw = (await params).week;
  if (!/^\d{1,2}$/.test(raw)) notFound();
  permanentRedirect(`/predictions?week=${Number.parseInt(raw, 10)}`);
}
