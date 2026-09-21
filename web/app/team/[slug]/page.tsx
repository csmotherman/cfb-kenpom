import type { Metadata } from "next";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import { buildTeamSeoParts } from "@/components/seo/TeamSeoContent";
import { noIndexMetadata } from "@/lib/seo";
import { getDataTimestamp, getTeamContent, getTeamDirectory, getTeamSnapshot } from "@/lib/seoData";
import { teamJsonLd, teamMetadata } from "@/lib/seoPages";
import TeamClient from "./TeamClient";

type Params = { params: Promise<{ slug: string }> };

export async function generateStaticParams() {
  return (await getTeamDirectory()).map((team) => ({ slug: team.slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const snapshot = await getTeamSnapshot(slug);
  if (!snapshot) return noIndexMetadata("Team not found", "This team is not in the PRIME ratings.");
  return teamMetadata(snapshot);
}

export default async function TeamPage({ params }: Params) {
  const { slug } = await params;
  const snapshot = await getTeamSnapshot(slug);
  if (snapshot === null) notFound();
  if (snapshot === undefined) return <TeamClient slug={slug} fullName={slug} seo={null} />;
  const content = await getTeamContent(snapshot);
  return (
    <>
      <JsonLd data={teamJsonLd(snapshot, await getDataTimestamp())} />
      <TeamClient slug={slug} fullName={snapshot.fullName} seo={buildTeamSeoParts(content)} />
    </>
  );
}
