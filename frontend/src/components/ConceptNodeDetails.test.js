import { render, screen } from "@testing-library/react";
import ConceptNodeDetails, { splitDocumentSource } from "./ConceptNodeDetails";

const WIKI = "https://en.wikipedia.org/wiki/Photosynthesis";

function renderNode(node) {
  const full = { id: "n1", label: "Chlorophyll", definition: "A green pigment.", ...node };
  return render(<ConceptNodeDetails node={full} onClose={() => {}} allNodes={[full]} allEdges={[]} />);
}

test("a document source shows its file and page, a web source stays a link", () => {
  renderNode({ source_type: "both", sources: ["week 3, plants.pdf — p. 4", WIKI] });

  expect(screen.getByText(/week 3, plants\.pdf/)).toHaveTextContent("📄 week 3, plants.pdf · page 4");
  expect(screen.getByRole("link")).toHaveAttribute("href", WIKI);
  expect(screen.getByText("🔗 Mixed")).toBeInTheDocument();
});

test("a map saved before Day 17 (sources stored comma-joined) still renders its sources", () => {
  // The API splits the old "biology_notes.pdf,https://…" column into a list (decode_sources);
  // its document entries carry no page.
  renderNode({ source_type: "document", sources: ["biology_notes.pdf", WIKI] });

  expect(screen.getByText(/biology_notes\.pdf/)).toHaveTextContent(/^📄 biology_notes\.pdf$/);
  expect(screen.queryByText(/page/)).toBeNull();
  expect(screen.getByRole("link")).toHaveAttribute("href", WIKI);
});

test("a node with no sources has no Sources section", () => {
  renderNode({ source_type: "unknown", sources: [] });

  expect(screen.queryByText(/Sources/)).toBeNull();
});

test.each([
  ["notes.pdf — p. 12", { file: "notes.pdf", page: "12" }],
  ["a — p. b — p. 3", { file: "a — p. b", page: "3" }],
  ["slides.pptx", { file: "slides.pptx", page: null }],
])("splitDocumentSource(%p)", (source, expected) => {
  expect(splitDocumentSource(source)).toEqual(expected);
});
