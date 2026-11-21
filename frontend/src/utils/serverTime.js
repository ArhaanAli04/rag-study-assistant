// Times from the backend (Day 19). Most routes send naive UTC times ("2026-11-19T10:00:00", from
// datetime.utcnow()); new Date() reads a time without a zone as *local* time, which shifts it by the
// browser's UTC offset (5h30 in India). Every screen parses server times through parseServerTime.

export function parseServerTime(value) {
  if (!value) return null;
  const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const countOf = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

export function formatShortDate(date, now = new Date()) {
  const options = { month: "short", day: "numeric" };
  if (date.getFullYear() !== now.getFullYear()) options.year = "numeric";
  return date.toLocaleDateString("en-US", options);
}

export function formatRelativeTime(date, now = new Date()) {
  const elapsed = now - date;
  if (elapsed < MINUTE) return "just now";
  if (elapsed < HOUR) return `${countOf(Math.floor(elapsed / MINUTE), "minute")} ago`;
  if (elapsed < DAY) return `${countOf(Math.floor(elapsed / HOUR), "hour")} ago`;
  if (elapsed < 2 * DAY) return "yesterday";
  if (elapsed < 7 * DAY) return `${Math.floor(elapsed / DAY)} days ago`;
  return formatShortDate(date, now);
}

// A server time as the browser's local date and time, or `fallback` when there is none.
export function formatServerDateTime(value, options = {}, fallback = "") {
  const date = parseServerTime(value);
  return date ? date.toLocaleString(undefined, options) : fallback;
}
