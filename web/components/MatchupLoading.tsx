export default function MatchupLoading({ detail = "Preparing your matchup" }: { detail?: string }) {
  return (
    <div className="matchup-loading" role="status" aria-live="polite" aria-busy="true">
      <span className="matchup-loading__ring" aria-hidden="true" />
      <strong>PRIME</strong>
      <span>{detail}</span>
    </div>
  );
}
