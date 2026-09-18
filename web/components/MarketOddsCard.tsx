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

  return (
    <div className={`market-odds-card${compact ? " market-odds-card--compact" : ""}`}>
      <div className="market-odds-card__head">
        <span>Market</span>
        <em>{quote.provider || "CFBD"}</em>
      </div>
      <div className="market-odds-card__grid">
        <span>
          <small>Spread</small>
          <strong>{spreadLabel(market)}</strong>
        </span>
        <span>
          <small>Moneyline</small>
          <strong>{market.awayTeam} {odds(quote.awayMoneyline)}</strong>
          <b>{market.homeTeam} {odds(quote.homeMoneyline)}</b>
        </span>
        <span>
          <small>Total</small>
          <strong>{quote.overUnder === null ? "—" : `O/U ${number(quote.overUnder)}`}</strong>
        </span>
      </div>
    </div>
  );
}
