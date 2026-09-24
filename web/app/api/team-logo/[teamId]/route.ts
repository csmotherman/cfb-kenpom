export const runtime = "nodejs";

const CACHE_HEADERS = {
  "Cache-Control": "public, max-age=86400, s-maxage=2592000, stale-while-revalidate=604800",
};

export async function GET(
  request: Request,
  { params }: { params: Promise<{ teamId: string }> }
) {
  const { teamId } = await params;

  if (!/^\d+$/.test(teamId)) {
    return new Response("Invalid team id.", { status: 400 });
  }

  // 128 by default; the team card asks for 256 so its 2x export stays sharp.
  const size = new URL(request.url).searchParams.get("size") === "256" ? 256 : 128;
  const source = `https://cdn.collegefootballdata.com/logos/${size}/${teamId}.png`;

  try {
    const response = await fetch(source, {
      next: { revalidate: 2592000 },
    });

    if (!response.ok) {
      return new Response("Logo not found.", { status: response.status });
    }

    const bytes = await response.arrayBuffer();

    return new Response(bytes, {
      status: 200,
      headers: {
        ...CACHE_HEADERS,
        "Content-Type": response.headers.get("content-type") || "image/png",
      },
    });
  } catch (error) {
    console.error("Failed to proxy team logo", error);
    return new Response("Logo unavailable.", { status: 502 });
  }
}
