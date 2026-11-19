import { act, fireEvent, render, screen, within } from "@testing-library/react";
import ProjectPanel from "./ProjectPanel";
import { projectDeletedNotice } from "../services/projectsApi";

const DL = {
  id: 3, name: "DL Unit 5", description: null, instructions: "Be brief.", created_at: "2026-11-19T10:00:00",
  archived: false, document_count: 2, chat_count: 1, last_activity: null,
};

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

function renderPanel(props = {}) {
  const onChanged = jest.fn(() => Promise.resolve());
  const onRetry = jest.fn();
  render(<ProjectPanel projects={[DL]} loading={false} error={null} onRetry={onRetry} onChanged={onChanged} {...props} />);
  return { onChanged, onRetry };
}

function requestsTo(method, path) {
  return global.fetch.mock.calls.filter(([url, options = {}]) =>
    (options.method || "GET") === method && new URL(url).pathname + new URL(url).search === path);
}

beforeEach(() => {
  localStorage.setItem("token", "jwt-for-demo");
});

// --- the list: loading, error, empty ---------------------------------------------------------------

test("while projects load the panel says so", () => {
  renderPanel({ projects: [], loading: true });

  expect(screen.getByRole("status")).toHaveTextContent("Loading projects…");
});

test("a failed load shows the error and a retry", () => {
  const { onRetry } = renderPanel({ projects: [], error: "Request failed" });

  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load your projects: Request failed");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(onRetry).toHaveBeenCalled();
});

test("with no projects the panel suggests one per course", () => {
  renderPanel({ projects: [] });

  expect(screen.getByText(/No projects yet. Create one per course/)).toBeInTheDocument();
});

test("a project shows its name and its file and chat counts", () => {
  renderPanel();

  const row = screen.getByRole("listitem", { name: "Project DL Unit 5" });
  expect(within(row).getByText("2 files · 1 chat")).toBeInTheDocument();
  expect(within(row).queryByText("Archived")).toBeNull();
});

// --- create -----------------------------------------------------------------------------------------

test("creating a project posts its name, shows progress and reports success", async () => {
  let finish;
  mockFetch({ "POST /projects": () => new Promise((resolve) => { finish = resolve; }) });
  const { onChanged } = renderPanel({ projects: [] });

  fireEvent.change(screen.getByLabelText("New project name"), { target: { value: "  BDA  " } });
  fireEvent.click(screen.getByRole("button", { name: /create project/i }));

  expect(screen.getByRole("button", { name: /creating…/i })).toBeDisabled();
  expect(JSON.parse(requestsTo("POST", "/projects")[0][1].body)).toEqual({ name: "BDA" });
  await act(async () => finish({ ok: true, status: 201, json: () => Promise.resolve({ ...DL, id: 9, name: "BDA" }) }));

  expect(onChanged).toHaveBeenCalledWith("Created project BDA.");
  expect(screen.getByLabelText("New project name")).toHaveValue("");
});

test("an empty name is refused before any request", () => {
  mockFetch({});
  renderPanel({ projects: [] });

  fireEvent.click(screen.getByRole("button", { name: /create project/i }));

  expect(screen.getByRole("alert")).toHaveTextContent("Give the project a name.");
  expect(global.fetch).not.toHaveBeenCalled();
});

test("a duplicate name shows the server's message", async () => {
  mockFetch({ "POST /projects": () => respond(409, { detail: "You already have a project named “DL Unit 5”." }) });
  const { onChanged } = renderPanel();

  fireEvent.change(screen.getByLabelText("New project name"), { target: { value: "DL Unit 5" } });
  fireEvent.click(screen.getByRole("button", { name: /create project/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent("You already have a project named");
  expect(onChanged).not.toHaveBeenCalled();
});

// --- rename, instructions, archive ------------------------------------------------------------------

test("renaming sends only the new name", async () => {
  mockFetch({ "PATCH /projects/3": () => respond(200, { ...DL, name: "DL Unit 6" }) });
  const { onChanged } = renderPanel();

  fireEvent.click(screen.getByRole("button", { name: /rename/i }));
  fireEvent.change(screen.getByLabelText("New name for DL Unit 5"), { target: { value: "DL Unit 6" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save name" })));

  expect(JSON.parse(requestsTo("PATCH", "/projects/3")[0][1].body)).toEqual({ name: "DL Unit 6" });
  expect(onChanged).toHaveBeenCalledWith("Renamed to DL Unit 6.");
});

test("the instructions editor counts characters, saves, and shows a failure next to it", async () => {
  let reply = () => respond(200, DL);
  mockFetch({ "PATCH /projects/3": () => reply() });
  renderPanel();

  fireEvent.click(screen.getByRole("button", { name: /instructions/i }));
  const box = screen.getByLabelText(/Instructions for every chat in DL Unit 5/);
  expect(box).toHaveValue("Be brief.");
  expect(screen.getByText("9 / 4000")).toBeInTheDocument();
  expect(box).toHaveAttribute("maxLength", "4000");

  fireEvent.change(box, { target: { value: "Use bullet points." } });
  expect(screen.getByText("18 / 4000")).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save instructions" })));
  expect(JSON.parse(requestsTo("PATCH", "/projects/3")[0][1].body)).toEqual({ instructions: "Use bullet points." });
  expect(screen.getByRole("status")).toHaveTextContent("Saved");

  reply = () => respond(422, { detail: "String should have at most 4000 characters" });
  fireEvent.change(box, { target: { value: "Again." } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save instructions" })));
  expect(screen.getByRole("alert")).toHaveTextContent("at most 4000 characters");
});

test("archive and unarchive toggle the flag", async () => {
  mockFetch({ "PATCH /projects/3": () => respond(200, DL) });
  const { onChanged } = renderPanel();

  await act(async () => fireEvent.click(screen.getByRole("button", { name: /^archive$/i })));

  expect(JSON.parse(requestsTo("PATCH", "/projects/3")[0][1].body)).toEqual({ archived: true });
  expect(onChanged).toHaveBeenCalledWith("Archived DL Unit 5: it takes no new files or chats.");
});

test("an archived project is marked and offers Unarchive", () => {
  renderPanel({ projects: [{ ...DL, archived: true }] });

  expect(screen.getByText("Archived")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /unarchive/i })).toBeInTheDocument();
});

// --- files and chats (GET /projects/{id}) -----------------------------------------------------------

test("expanding a project loads its files and chats", async () => {
  let finish;
  mockFetch({ "GET /projects/3": () => new Promise((resolve) => { finish = resolve; }) });
  renderPanel();

  fireEvent.click(screen.getByRole("button", { name: "Show files and chats of DL Unit 5" }));
  expect(screen.getByRole("status")).toHaveTextContent("Loading files and chats…");
  await act(async () => finish({ ok: true, status: 200, json: () => Promise.resolve({
    ...DL,
    documents: [{ id: 1, filename: "rnn.pdf", version: 1, created_at: null, chunks: 12 },
                { id: 2, filename: "scan.pdf", version: 1, created_at: null, chunks: 0 }],
    chats: [{ id: 5, title: "LSTM gates", topic: "General", created_at: null, last_message_time: null }],
  }) }));

  expect(screen.getByText("rnn.pdf")).toBeInTheDocument();
  expect(screen.getByText("scan.pdf (not searchable yet)")).toBeInTheDocument();
  expect(screen.getByText("LSTM gates")).toBeInTheDocument();
});

test("an empty project says so, and a failed load offers a retry", async () => {
  let reply = () => respond(500, { detail: "Internal server error. Please try again later." });
  mockFetch({ "GET /projects/3": () => reply() });
  renderPanel();

  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Show files and chats of DL Unit 5" })));
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this project");

  reply = () => respond(200, { ...DL, documents: [], chats: [] });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Try again" })));
  expect(screen.getByText("No files or chats in this project yet.")).toBeInTheDocument();
});

// --- delete -----------------------------------------------------------------------------------------

test("deleting asks what happens to the files and sends that choice", async () => {
  mockFetch({ "DELETE /projects/3?documents=unassign": () => respond(200, {
    status: "deleted", project_id: 3, documents: "unassign", documents_deleted: 0,
    documents_unassigned: 2, chats_unassigned: 1, doc_version: 4,
  }) });
  const { onChanged } = renderPanel();

  fireEvent.click(screen.getByRole("button", { name: /delete$/i }));
  const dialog = screen.getByRole("dialog", { name: "Delete DL Unit 5" });
  expect(dialog).toHaveTextContent("1 chat will move to No project. What should happen to its 2 files?");
  const confirm = within(dialog).getByRole("button", { name: "Delete project" });
  expect(confirm).toBeDisabled(); // no default: the user must choose

  fireEvent.click(within(dialog).getByLabelText(/Keep them/));
  await act(async () => fireEvent.click(confirm));

  expect(requestsTo("DELETE", "/projects/3?documents=unassign")).toHaveLength(1);
  expect(onChanged).toHaveBeenCalledWith("Deleted project DL Unit 5. 2 files moved to No project. Its 1 chat moved to No project.");
});

test("a refused delete shows why and keeps the project", async () => {
  mockFetch({ "DELETE /projects/3?documents=unassign": () => respond(409, {
    detail: "No project already has a file named notes.pdf. Rename or delete one of them first.",
  }) });
  const { onChanged } = renderPanel();

  fireEvent.click(screen.getByRole("button", { name: /delete$/i }));
  fireEvent.click(screen.getByLabelText(/Keep them/));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Delete project" })));

  expect(screen.getByRole("alert")).toHaveTextContent("already has a file named notes.pdf");
  expect(onChanged).not.toHaveBeenCalled();
});

test.each([
  [{ documents: "delete", documents_deleted: 2, chats_unassigned: 0 }, "Deleted project DL and 2 files."],
  [{ documents: "delete", documents_deleted: 1, chats_unassigned: 3 }, "Deleted project DL and 1 file. Its 3 chats moved to No project."],
  [{ documents: "unassign", documents_unassigned: 0, chats_unassigned: 0 }, "Deleted project DL. 0 files moved to No project."],
])("delete notice for %o", (result, expected) => {
  expect(projectDeletedNotice("DL", result)).toBe(expected);
});
