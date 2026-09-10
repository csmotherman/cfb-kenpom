"use client";

type Props = {
  updatedAt: string | null;
};

export default function TableUpdatedAt({ updatedAt }: Props) {
  if (!updatedAt) return null;

  const value = new Date(updatedAt);
  const label = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Detroit",
    timeZoneName: "short",
  }).format(value);

  return (
    <div className="table-updated-at">
      <span>Updated at</span>
      <time dateTime={updatedAt}>{label}</time>
    </div>
  );
}
