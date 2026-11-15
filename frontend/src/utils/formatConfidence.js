// A map's confidence arrives as a raw 0–100 float (46.282801862394514); show it as a whole percent.
export function formatConfidence(value) {
  const number = Number(value);
  if (value === null || value === undefined || Number.isNaN(number)) return "—";
  return `${Math.round(number)}%`;
}
