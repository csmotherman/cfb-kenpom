import type { MarketGame } from "@/lib/types";

function odds(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${value}` : String(value);
}

function number(value: number | null): string {
  if (value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function spreadLabel(market: MarketGame): string {
  const quote = market.primary;
  if (!quote) return "—";
  if (quote.formattedSpread) return quote.formattedSpread;
  if (quote.spread === null) return "—";
  if (quote.spread === 0) return "PK";
  if (quote.spread < 0) return `${market.homeTeam} ${quote.spread.toFixed(1)}`;
  return `${market.awayTeam} ${(-quote.spread).toFixed(1)}`;
}

// CFBD distinguishes the opening line from the current/closing one via
// spreadOpen/overUnderOpen; only note the open when it's both known and
// actually different from where the line ended up, so a game with no real
// movement doesn't show a redundant second line.
function openingSpreadNote(quote: { spread: number | null; spreadOpen: number | null }): string | null {
  if (quote.spreadOpen === null || quote.spread === null || quote.spreadOpen === quote.spread) return null;
  return `Opened ${quote.spreadOpen > 0 ? "+" : ""}${quote.spreadOpen.toFixed(1)}`;
}

function openingTotalNote(quote: { overUnder: number | null; overUnderOpen: number | null }): string | null {
  if (quote.overUnderOpen === null || quote.overUnder === null || quote.overUnderOpen === quote.overUnder) return null;
  return `Opened ${number(quote.overUnderOpen)}`;
}

export default function MarketOddsCard({
  market,
  compact = false,
}: {
  market: MarketGame | null | undefined;
  compact?: boolean;
}) {
  const quote = market?.primary ?? null;
  if (!market || !quote) {
    return (
      <div className={`market-odds-card${compact ? " market-odds-card--compact" : ""} market-odds-card--empty`}>
        <div className="market-odds-card__head">
          <span>Market</span>
          <em>Odds unavailable</em>
        </div>
      </div>
    );
  }

  const spreadNote = openingSpreadNote(quote);
  const totalNote = openingTotalNote(quote);

  return (
    <div className={`market-odds-card${compact ? " market-odds-card--compact" : ""}`}>
      <div className="market-odds-card__head">
        <span>{market.frozen ? "Pregame Market · Final" : "Market"}</span>
        <em>{quote.provider || "CFBD"}</em>
      </div>
      <div className="market-odds-card__grid">
        <span>
          <small>Spread</small>
          <strong>{spreadLabel(market)}</strong>
          {spreadNote ? <b>{spreadNote}</b> : null}
        </span>
        <span>
          <small>Moneyline</small>
          <strong>{market.awayTeam} {odds(quote.awayMoneyline)}</strong>
          <b>{market.homeTeam} {odds(quote.homeMoneyline)}</b>
        </span>
        <span>
          <small>Total</small>
          <strong>{quote.overUnder === null ? "—" : `O/U ${number(quote.overUnder)}`}</strong>
          {totalNote ? <b>{totalNote}</b> : null}
        </span>
      </div>
    </div>
  );
}
