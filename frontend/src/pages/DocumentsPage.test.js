import { TextDecoder, TextEncoder } from "util";

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide.
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { fireEvent, render, screen } = require("@testing-library/react");
const { MemoryRouter } = require("react-router-dom");
const { AuthProvider } = require("../contexts/AuthContext");
const DocumentsPage = require("./DocumentsPage").default;
const { deleteNotice, uploadNotice } = require("../utils/uploadNotice");

const NOTES = { id: 7, filename: "notes.pdf", path: "uploads/1/a.pdf", created_at: null, file_size: 2048, version: 1, chunks: 12 };

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function mockApi({ documents, upload }) {
  global.fetch = jest.fn((url, options = {}) => {
    if (url.endsWith("/upload")) return upload();
    if (url.endsWith("/documents")) return respond(200, documents);
    return respond(200, {});
  });
}

function renderPage() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/documents"]}>
        <DocumentsPage />
      </MemoryRouter>
    </AuthProvider>
  );
}

async function uploadAFile() {
  const file = new File(["%PDF-1.4"], "notes.pdf", { type: "application/pdf" });
  fireEvent.change(document.getElementById("file-upload"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: /upload document/i }));
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("token", "jwt-for-demo");
  localStorage.setItem("userEmail", "demo@example.com");
});

test("while an upload is in progress the page says large files can take a few minutes", async () => {
  let finishUpload;
  mockApi({
    documents: [],
    upload: () => new Promise((resolve) => {
      finishUpload = () => resolve({ ok: true, status: 200, json: () => Promise.resolve(
        { filename: "notes.pdf", document_id: 7, status: "new", version: 1, chunks_indexed: 12, doc_version: 1 }) });
    }),
  });
  renderPage();
  await screen.findByText("No documents yet");
  expect(screen.queryByText(/large files can take a few minutes/i)).not.toBeInTheDocument();

  await uploadAFile();

  expect(await screen.findByRole("note")).toHaveTextContent("Large files can take a few minutes to index.");
  finishUpload();
  expect(await screen.findByRole("status")).toBeInTheDocument();
  expect(screen.queryByText(/large files can take a few minutes/i)).not.toBeInTheDocument();
});

test("an identical re-upload says it is already indexed instead of silently doing nothing", async () => {
  mockApi({
    documents: [NOTES],
    upload: () => respond(200, { filename: "notes.pdf", document_id: 7, status: "unchanged", version: 1, chunks_indexed: 0, doc_version: 1 }),
  });
  renderPage();
  await screen.findByText("notes.pdf");

  await uploadAFile();

  expect(await screen.findByRole("status")).toHaveTextContent("notes.pdf is already indexed — nothing changed");
});

test("a failed indexing shows the server's message and no success notice", async () => {
  mockApi({
    documents: [],
    upload: () => respond(502, { detail: "The file was saved but could not be indexed. Please upload it again." }),
  });
  renderPage();
  await screen.findByText(/no documents yet/i);

  await uploadAFile();

  expect(await screen.findByRole("alert")).toHaveTextContent("could not be indexed. Please upload it again.");
  expect(screen.queryByRole("status")).toBeNull();
});

test("a document with no searchable chunks is marked, an indexed one is not", async () => {
  mockApi({
    documents: [NOTES, { ...NOTES, id: 8, filename: "old-slides.pptx", chunks: 0 }],
    upload: () => respond(200, {}),
  });
  renderPage();

  await screen.findByText("old-slides.pptx");

  expect(screen.getAllByText(/not searchable yet/i)).toHaveLength(1);
});

test.each([
  [{ status: "new", filename: "a.pdf", chunks_indexed: 1 }, "Indexed 1 passage from a.pdf."],
  [{ status: "new", filename: "scan.pdf", chunks_indexed: 0 }, "scan.pdf was saved, but no text was found in it to search."],
  [{ status: "changed", filename: "a.pdf", version: 2, chunks_indexed: 5 }, "Version 2 of a.pdf indexed (5 passages)."],
  [{ status: "reindexed", filename: "a.pdf", chunks_indexed: 3 }, "a.pdf is searchable again — indexed 3 passages."],
])("upload notice for %o", (result, expected) => {
  expect(uploadNotice(result)).toContain(expected);
});

test("the delete notice names every version that went", () => {
  expect(deleteNotice("notes.pdf", 1)).toBe("Deleted notes.pdf. New answers won't cite it.");
  expect(deleteNotice("notes.pdf", 3)).toBe("Deleted notes.pdf (all 3 versions). New answers won't cite it.");
});
