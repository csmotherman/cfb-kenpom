"use client";

import Link from "next/link";
import { useState } from "react";
import type { TeamCardData } from "@/lib/teamCardData";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function TeamCardClient({ data }: { data: TeamCardData }) {
  const [status, setStatus] = useState("");
  const [working, setWorking] = useState(false);
  const imageUrl =
    "/team/" +
    data.slug +
    "/card/image?season=" +
    data.year +
    "&week=" +
    data.week;
  const filename = "prime-" + data.slug + "-" + data.year + "-team-card.png";

  async function getPng() {
    const response = await fetch(imageUrl, { cache: "no-store" });
    if (!response.ok) throw new Error("Image generation failed.");
    return response.blob();
  }

  async function copyPng() {
    if (working) return;
    setWorking(true);
    setStatus("");
    try {
      const blob = await getPng();
      if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        setStatus("Copied PNG to clipboard.");
      } else {
        downloadBlob(blob, filename);
        setStatus("PNG downloaded — image clipboard is not supported in this browser.");
      }
    } catch {
      setStatus("Could not copy the PNG. Try Download PNG instead.");
    } finally {
      setWorking(false);
    }
  }

  async function downloadPng() {
    if (working) return;
    setWorking(true);
    setStatus("");
    try {
      downloadBlob(await getPng(), filename);
      setStatus("PNG downloaded.");
    } catch {
      setStatus("Could not generate the PNG.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="ct-page ct-team-card-page">
      <div className="ct-actions">
        <Link href={"/team/" + data.slug}>← Team Profile</Link>
        <div>
          <button type="button" onClick={downloadPng} disabled={working}>Download PNG</button>
          <button className="primary" type="button" onClick={copyPng} disabled={working}>
            {working ? "Generating…" : "Copy PNG"}
          </button>
        </div>
        {status ? <p role="status">{status}</p> : null}
      </div>

      <div className="ct-generated-card-wrap">
        {/* The preview intentionally uses the exact PNG endpoint used by Copy/Download,
            so users never see a card that differs from the exported asset. */}
        <img
          className="ct-generated-card"
          src={imageUrl}
          alt={data.team + " " + data.year + " PRIME team profile card"}
        />
      </div>
    </main>
  );
}
