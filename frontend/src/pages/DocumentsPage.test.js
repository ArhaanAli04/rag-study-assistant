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

// --- Day 18: projects on the Documents page -----------------------------------------------------------

const DL = { id: 3, name: "DL Unit 5", description: null, instructions: null, created_at: "2026-11-19T10:00:00",
  archived: false, document_count: 1, chat_count: 0, last_activity: null };
const OLD = { ...DL, id: 4, name: "Old course", archived: true };
const IN_DL = { ...NOTES, id: 8, filename: "rnn.pdf", project_id: 3, project_name: "DL Unit 5" };
const LOOSE = { ...NOTES, project_id: null, project_name: null };

function mockProjectsApi({ documents = [LOOSE, IN_DL], projects = [DL, OLD], upload, move } = {}) {
  global.fetch = jest.fn((url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method || "GET";
    if (pathname === "/projects") return projects instanceof Error ? respond(500, { detail: projects.message }) : respond(200, projects);
    if (pathname === "/upload") return (upload || (() => respond(200, { filename: "notes.pdf", status: "new", chunks_indexed: 3 })))(options);
    if (pathname === "/documents") return respond(200, documents);
    if (method === "PATCH" && pathname.startsWith("/documents/")) return (move || (() => respond(200, { status: "moved" })))(options);
    return respond(200, {});
  });
}

test("each document shows its project, or No project", async () => {
  mockProjectsApi();
  renderPage();

  await screen.findByText("rnn.pdf");

  expect(screen.getByTestId("project-of-8")).toHaveTextContent("DL Unit 5");
  expect(screen.getByTestId("project-of-7")).toHaveTextContent("No project");
});

test("an upload goes into the chosen project; archived projects aren't offered", async () => {
  mockProjectsApi();
  renderPage();
  await screen.findByText("rnn.pdf");
  const picker = screen.getByLabelText("Project");
  expect(Array.from(picker.options).map((o) => o.textContent)).toEqual(["No project", "DL Unit 5"]);

  fireEvent.change(picker, { target: { value: "3" } });
  await uploadAFile();
  await screen.findByRole("status");

  const [, options] = global.fetch.mock.calls.find(([url]) => new URL(url).pathname === "/upload");
  expect(options.body.get("project_id")).toBe("3");
});

test("an upload with No project sends no project_id", async () => {
  mockProjectsApi();
  renderPage();
  await screen.findByText("rnn.pdf");

  await uploadAFile();
  await screen.findByRole("status");

  const [, options] = global.fetch.mock.calls.find(([url]) => new URL(url).pathname === "/upload");
  expect(options.body.has("project_id")).toBe(false);
});

test("the filter shows one project's documents, and says when a project has none", async () => {
  mockProjectsApi({ projects: [DL, { ...DL, id: 5, name: "BDA" }] });
  renderPage();
  await screen.findByText("rnn.pdf");
  const filter = screen.getByLabelText("Show");

  fireEvent.change(filter, { target: { value: "3" } });
  expect(screen.getByText("rnn.pdf")).toBeInTheDocument();
  expect(screen.queryByText("notes.pdf")).toBeNull();

  fireEvent.change(filter, { target: { value: "none" } });
  expect(screen.getByText("notes.pdf")).toBeInTheDocument();
  expect(screen.queryByText("rnn.pdf")).toBeNull();

  fireEvent.change(filter, { target: { value: "5" } });
  expect(screen.getByText("No documents in this project yet.")).toBeInTheDocument();
});

test("moving a document sends its new project and refreshes the list", async () => {
  mockProjectsApi();
  renderPage();
  await screen.findByText("notes.pdf");

  fireEvent.change(screen.getByLabelText("Move notes.pdf to a project"), { target: { value: "3" } });

  expect(await screen.findByRole("status")).toHaveTextContent("Moved notes.pdf to DL Unit 5.");
  const [url, options] = global.fetch.mock.calls.find(([, o = {}]) => o.method === "PATCH");
  expect(new URL(url).pathname).toBe("/documents/7");
  expect(JSON.parse(options.body)).toEqual({ project_id: 3 });
});

test("a document in a project can move back to No project", async () => {
  mockProjectsApi();
  renderPage();
  await screen.findByText("rnn.pdf");

  fireEvent.change(screen.getByLabelText("Move rnn.pdf to a project"), { target: { value: "none" } });

  expect(await screen.findByRole("status")).toHaveTextContent("Moved rnn.pdf to No project.");
  const [, options] = global.fetch.mock.calls.find(([, o = {}]) => o.method === "PATCH");
  expect(JSON.parse(options.body)).toEqual({ project_id: null });
});

test("a refused move shows the server's reason", async () => {
  mockProjectsApi({ move: () => respond(409, { detail: "That project already has a file named notes.pdf. Rename or delete one of them first." }) });
  renderPage();
  await screen.findByText("notes.pdf");

  fireEvent.change(screen.getByLabelText("Move notes.pdf to a project"), { target: { value: "3" } });

  expect(await screen.findByRole("alert")).toHaveTextContent("already has a file named notes.pdf");
  expect(screen.queryByRole("status")).toBeNull();
});

test("if projects fail to load, documents still list and uploads still work without a project", async () => {
  mockProjectsApi({ projects: new Error("Request failed") });
  renderPage();

  expect(await screen.findByText("notes.pdf")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your projects");
  expect(Array.from(screen.getByLabelText("Project").options).map((o) => o.textContent)).toEqual(["No project"]);
});

test("the delete notice names every version that went", () => {
  expect(deleteNotice("notes.pdf", 1)).toBe("Deleted notes.pdf. New answers won't cite it.");
  expect(deleteNotice("notes.pdf", 3)).toBe("Deleted notes.pdf (all 3 versions). New answers won't cite it.");
});
