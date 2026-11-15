import { render, screen } from "@testing-library/react";
import MapListView from "./MapListView";
import { formatConfidence } from "../utils/formatConfidence";

const MAP = {
  id: 1,
  topic: "Photosynthesis",
  created_at: "2026-11-15T12:00:00",
  node_count: 12,
  edge_count: 11,
  sources: { documents: 4, web: 0 },
  confidence: 46.282801862394514, // what the Day 17 live check showed unrounded
};

test("a map card shows its confidence as a whole percent", () => {
  render(<MapListView maps={[MAP]} loading={false} onViewMap={() => {}} onDeleteMap={() => {}} />);

  expect(screen.getByText("46% confident")).toBeInTheDocument();
  expect(screen.queryByText(/46\.28/)).toBeNull();
});

test.each([
  [46.282801862394514, "46%"],
  [46.5, "47%"],
  [0, "0%"],
  [100, "100%"],
  ["70.4", "70%"],
  [null, "—"],
  [undefined, "—"],
  ["n/a", "—"],
])("formatConfidence(%p) is %p", (value, expected) => {
  expect(formatConfidence(value)).toBe(expected);
});
