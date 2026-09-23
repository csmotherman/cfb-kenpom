export default function MatchupLoading() {
  return (
    <div className="matchup-loading" role="status" aria-live="polite">
      <span className="matchup-loading__ring" aria-hidden="true" />
      <strong>PRIME</strong>
      <span>Preparing your matchup</span>
    </div>
  );
}
