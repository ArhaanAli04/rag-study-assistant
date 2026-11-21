import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider } from "../contexts/AuthContext";
import ProjectDetailPage from "./ProjectDetailPage";

jest.mock("../components/TopNav", () => () => null);

const DL = {
  id: 3, name: "DL Unit 5", description: "RNNs and attention", instructions: "Be brief.",
  created_at: "2026-11-19T10:00:00", archived: false, document_count: 2, chat_count: 1, last_activity: null,
  documents: [
    { id: 1, filename: "rnn.pdf", version: 2, created_at: "2026-11-20T09:00:00", chunks: 12 },
    { id: 2, filename: "scan.pdf", version: 1, created_at: null, chunks: 0 },
  ],
  chats: [{ id: 5, title: "LSTM gates", topic: "Deep Learning", created_at: null, last_message_time: null }],
};
const EMPTY = { ...DL, document_count: 0, chat_count: 0, documents: [], chats: [] };

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

// routes: { "METHOD /path": () => response }; anything else is a test failure.
function mockFetch(routes) {
  global.fetch = jest.fn((url, options = {}) => {
    const path = new URL(url).pathname + new URL(url).search;
    const key = `${options.method || "GET"} ${path}`;
    if (!routes[key]) throw new Error(`unexpected request ${key}`);
    return routes[key](options);
  });
}

function requestsTo(method, path) {
  return global.fetch.mock.calls.filter(([url, options = {}]) =>
    (options.method || "GET") === method && new URL(url).pathname + new URL(url).search === path);
}

function ProjectsProbe() {
  const location = useLocation();
  return <p data-testid="projects-page">{location.state?.notice}</p>;
}

function GoTo({ to }) {
  const navigate = useNavigate();
  return <button onClick={() => navigate(to)}>go to {to}</button>;
}

async function renderAt(url) {
  await act(async () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={[url]}>
          <GoTo to="/projects/4" />
          <Routes>
            <Route path="/projects" element={<ProjectsProbe />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );
  });
}

beforeEach(() => {
  localStorage.setItem("token", "jwt-for-demo");
});

// --- loading, not found, error ------------------------------------------------------------------

test("while the project loads the page says so", async () => {
  mockFetch({ "GET /projects/3": () => new Promise(() => {}) });
  await renderAt("/projects/3");

  expect(screen.getByRole("status")).toHaveTextContent("Loading project…");
});

test("another user's or a deleted project (404) is not found, with a way back", async () => {
  mockFetch({ "GET /projects/12": () => respond(404, { detail: "Project not found" }) });
  await renderAt("/projects/12");

  expect(screen.getByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to your projects" })).toHaveAttribute("href", "/projects");
});

test("a non-numeric id is not found without asking the server", async () => {
  mockFetch({});
  await renderAt("/projects/abc");

  expect(screen.getByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalled();
});

test("a failed load shows the error and retries", async () => {
  let reply = () => respond(500, { detail: "Internal server error. Please try again later." });
  mockFetch({ "GET /projects/3": () => reply() });
  await renderAt("/projects/3");

  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this project: Internal server error");
  reply = () => respond(200, DL);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Try again" })));
  expect(screen.getByRole("heading", { name: "DL Unit 5" })).toBeInTheDocument();
});

test("a reply for a project the user already left is dropped", async () => {
  let finish3;
  mockFetch({
    "GET /projects/3": () => new Promise((resolve) => { finish3 = resolve; }),
    "GET /projects/4": () => respond(200, { ...DL, id: 4, name: "BDA" }),
  });
  await renderAt("/projects/3");

  await act(async () => fireEvent.click(screen.getByRole("button", { name: "go to /projects/4" })));
  expect(screen.getByRole("heading", { name: "BDA" })).toBeInTheDocument();
  await act(async () => finish3({ ok: true, status: 200, json: () => Promise.resolve(DL) }));

  expect(screen.getByRole("heading", { name: "BDA" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "DL Unit 5" })).toBeNull();
});

// --- what the page shows ------------------------------------------------------------------------

test("the page shows the project, its files and chats, and starts chats in it", async () => {
  mockFetch({ "GET /projects/3": () => respond(200, DL) });
  await renderAt("/projects/3");

  expect(screen.getByRole("heading", { name: "DL Unit 5" })).toBeInTheDocument();
  expect(screen.getByText("RNNs and attention", { selector: "p" })).toBeInTheDocument();
  expect(screen.getByLabelText(/Description of DL Unit 5/)).toHaveValue("RNNs and attention");
  expect(screen.getByText(/2 files · 1 chat/)).toBeInTheDocument();

  const rnn = screen.getByRole("listitem", { name: "File rnn.pdf" });
  expect(within(rnn).getByText(/Version 2 · uploaded Nov 20/)).toBeInTheDocument();
  expect(within(rnn).queryByText(/Not searchable yet/)).toBeNull();
  expect(within(screen.getByRole("listitem", { name: "File scan.pdf" })).getByText(/Not searchable yet/)).toBeInTheDocument();

  expect(screen.getByRole("link", { name: /LSTM gates/ })).toHaveAttribute("href", "/chat?session=5");
  expect(screen.getByRole("link", { name: /New chat in this project/ })).toHaveAttribute("href", "/chat?project=3");
  expect(screen.getByLabelText(/Instructions for every chat in DL Unit 5/)).toHaveValue("Be brief.");
  expect(screen.queryByLabelText("Project")).toBeNull(); // the upload's project is fixed
});

test("an empty project suggests uploading and starting a chat", async () => {
  mockFetch({ "GET /projects/3": () => respond(200, EMPTY) });
  await renderAt("/projects/3");

  expect(screen.getByText(/No files yet. Upload this course's slides and notes./)).toBeInTheDocument();
  expect(screen.getByText("No chats yet.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Start one/ })).toHaveAttribute("href", "/chat?project=3");
});

// --- files --------------------------------------------------------------------------------------

test("an upload goes into this project and the list refreshes", async () => {
  let detail = EMPTY;
  mockFetch({
    "GET /projects/3": () => respond(200, detail),
    "POST /upload": () => respond(200, { filename: "rnn.pdf", status: "new", chunks_indexed: 4 }),
  });
  await renderAt("/projects/3");

  const file = new File(["%PDF-1.4"], "rnn.pdf", { type: "application/pdf" });
  fireEvent.change(document.getElementById("file-upload"), { target: { files: [file] } });
  detail = { ...DL, documents: [DL.documents[0]] };
  await act(async () => fireEvent.click(screen.getByRole("button", { name: /upload document/i })));

  const [, options] = requestsTo("POST", "/upload")[0];
  expect(options.body.get("project_id")).toBe("3");
  expect(screen.getByRole("status")).toHaveTextContent("Indexed 4 passages from rnn.pdf.");
  expect(screen.getByRole("listitem", { name: "File rnn.pdf" })).toBeInTheDocument();
});

test("a refused upload shows the server's reason in the upload box", async () => {
  mockFetch({
    "GET /projects/3": () => respond(200, EMPTY),
    "POST /upload": () => respond(409, { detail: "This project is archived. Unarchive it to add files or start chats." }),
  });
  await renderAt("/projects/3");

  fireEvent.change(document.getElementById("file-upload"), { target: { files: [new File(["x"], "a.pdf")] } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: /upload document/i })));

  expect(screen.getByText(/This project is archived/)).toBeInTheDocument();
});

test("Move to No project detaches the file and says what that means", async () => {
  mockFetch({
    "GET /projects/3": () => respond(200, DL),
    "PATCH /documents/1": () => respond(200, { status: "moved" }),
  });
  await renderAt("/projects/3");

  const rnn = screen.getByRole("listitem", { name: "File rnn.pdf" });
  await act(async () => fireEvent.click(within(rnn).getByRole("button", { name: /Move to No project/ })));

  expect(JSON.parse(requestsTo("PATCH", "/documents/1")[0][1].body)).toEqual({ project_id: null });
  expect(screen.getByRole("status")).toHaveTextContent("Moved rnn.pdf to No project");
});

test("deleting a file asks first, then deletes every version", async () => {
  mockFetch({
    "GET /projects/3": () => respond(200, DL),
    "DELETE /documents/1": () => respond(200, { status: "deleted", versions_deleted: 2 }),
  });
  window.confirm = jest.fn(() => false);
  await renderAt("/projects/3");

  fireEvent.click(screen.getByRole("button", { name: "Delete rnn.pdf" }));
  expect(requestsTo("DELETE", "/documents/1")).toHaveLength(0);

  window.confirm = jest.fn(() => true);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Delete rnn.pdf" })));
  expect(requestsTo("DELETE", "/documents/1")).toHaveLength(1);
  expect(screen.getByRole("status")).toHaveTextContent("Deleted rnn.pdf (all 2 versions).");
});

test("a failed move shows the server's reason", async () => {
  mockFetch({
    "GET /projects/3": () => respond(200, DL),
    "PATCH /documents/1": () => respond(409, { detail: "No project already has a file named rnn.pdf. Rename or delete one of them first." }),
  });
  await renderAt("/projects/3");

  await act(async () => fireEvent.click(within(screen.getByRole("listitem", { name: "File rnn.pdf" })).getByRole("button", { name: /Move to No project/ })));

  expect(screen.getByRole("alert")).toHaveTextContent("already has a file named rnn.pdf");
});

// --- archive, delete ----------------------------------------------------------------------------

test("an archived project hides the upload, can't start chats, and offers Unarchive", async () => {
  mockFetch({
    "GET /projects/3": () => respond(200, { ...DL, archived: true }),
    "PATCH /projects/3": () => respond(200, DL),
  });
  await renderAt("/projects/3");

  expect(screen.getByText(/This project is archived/)).toBeInTheDocument();
  expect(document.getElementById("file-upload")).toBeNull();
  expect(screen.getByRole("button", { name: /New chat in this project/ })).toBeDisabled();
  expect(screen.getByRole("link", { name: /LSTM gates/ })).toBeInTheDocument(); // old chats still open

  await act(async () => fireEvent.click(screen.getAllByRole("button", { name: /Unarchive/ })[0]));
  expect(JSON.parse(requestsTo("PATCH", "/projects/3")[0][1].body)).toEqual({ archived: false });
});

test("deleting the project returns to the projects list with the notice", async () => {
  mockFetch({
    "GET /projects/3": () => respond(200, DL),
    "DELETE /projects/3?documents=unassign": () => respond(200, {
      status: "deleted", project_id: 3, documents: "unassign", documents_deleted: 0,
      documents_unassigned: 2, chats_unassigned: 1, doc_version: 9,
    }),
  });
  await renderAt("/projects/3");

  fireEvent.click(screen.getByRole("button", { name: /^Delete$/ }));
  fireEvent.click(screen.getByLabelText(/Keep them/));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Delete project" })));

  expect(screen.getByTestId("projects-page")).toHaveTextContent(
    "Deleted project DL Unit 5. 2 files moved to No project. Its 1 chat moved to No project.");
});
