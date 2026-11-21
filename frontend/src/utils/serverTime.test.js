import { formatRelativeTime, formatServerDateTime, parseServerTime } from "./serverTime";

test("server times without a zone are read as UTC; zoned ones keep their zone", () => {
  expect(parseServerTime("2026-11-19T10:00:00").toISOString()).toBe("2026-11-19T10:00:00.000Z");
  expect(parseServerTime("2026-11-19T10:00:00.123456").toISOString()).toBe("2026-11-19T10:00:00.123Z");
  expect(parseServerTime("2026-11-19T10:00:00Z").toISOString()).toBe("2026-11-19T10:00:00.000Z");
  expect(parseServerTime("2026-11-19T10:00:00+05:30").toISOString()).toBe("2026-11-19T04:30:00.000Z");
  expect(parseServerTime("2026-11-19T10:00:00+00:00").toISOString()).toBe("2026-11-19T10:00:00.000Z");
});

test("missing or unreadable times are null", () => {
  expect(parseServerTime(null)).toBeNull();
  expect(parseServerTime("")).toBeNull();
  expect(parseServerTime("not a time")).toBeNull();
});

test.each([
  [30 * 1000, "just now"],
  [60 * 1000, "1 minute ago"],
  [5 * 60 * 1000, "5 minutes ago"],
  [3 * 3600 * 1000, "3 hours ago"],
  [30 * 3600 * 1000, "yesterday"],
  [3 * 86400 * 1000, "3 days ago"],
])("relative time %i ms ago is %s", (ms, expected) => {
  const now = new Date("2026-11-21T12:00:00Z");
  expect(formatRelativeTime(new Date(now - ms), now)).toBe(expected);
});

test("a naive server time formats as the same instant as its UTC form", () => {
  const options = { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false };
  expect(formatServerDateTime("2026-11-19T10:00:00", options)).toBe(formatServerDateTime("2026-11-19T10:00:00Z", options));
  expect(formatServerDateTime("2026-11-19T10:00:00", options)).toMatch(/15:30/);
  expect(formatServerDateTime(null, options, "Recently uploaded")).toBe("Recently uploaded");
});
