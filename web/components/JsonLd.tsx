import type { JsonLd as JsonLdObject } from "@/lib/seo";

/** Renders schema.org JSON-LD. "<" is escaped so data can never close the script tag. */
export default function JsonLd({ data }: { data: JsonLdObject | JsonLdObject[] }) {
  const json = JSON.stringify(data).replace(/</g, "\\u003c");
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}
