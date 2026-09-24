import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTeamDirectory } from "@/lib/seoData";
import { getTeamCardData } from "@/lib/teamCardData";
import TeamCardClient from "./TeamCardClient";

type Params = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export async function generateStaticParams() {
  return (await getTeamDirectory()).map((team) => ({ slug: team.slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const data = await getTeamCardData(slug);
  if (!data) return { title: "Team Card | PRIME", robots: { index: false, follow: false } };
  return {
    title: data.team + " Team Profile Card | PRIME",
    description: data.year + " " + data.team + " team profile from PRIME CFB Analytics.",
    robots: { index: false, follow: false },
  };
}

export default async function TeamCardPage({ params }: Params) {
  const { slug } = await params;
  const data = await getTeamCardData(slug);
  if (!data) notFound();
  return <TeamCardClient data={data} />;
}
