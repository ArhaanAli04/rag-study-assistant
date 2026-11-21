import { TextDecoder, TextEncoder } from "util";

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide.
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { act, fireEvent, render, screen, within } = require("@testing-library/react");
const { MemoryRouter } = require("react-router-dom");
const { AuthProvider } = require("../contexts/AuthContext");
const ProjectsPage = require("./ProjectsPage").default;
const { formatRelativeTime, lastActivityText, parseServerTime } = require("../services/projectsApi");

const DL = {
  id: 3, name: "DL Unit 5", description: "RNNs and attention", instructions: null, created_at: "2026-11-19T10:00:00",
  archived: false, document_count: 2, chat_count: 1, last_activity: null,
};
const BDA = { ...DL, id: 4, name: "BDA", description: null, document_count: 0, chat_count: 0 };

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

// routes: { "METHOD /path": () => response }; the TopNav's profile request is always answered.
function mockFetch(routes) {
  global.fetch = jest.fn((url, options = {}) => {
    const path = new URL(url).pathname + new URL(url).search;
    const key = `${options.method || "GET"} ${path}`;
    if (key === "GET /user/profile") return respond(200, {});
    if (!routes[key]) throw new Error(`unexpected request ${key}`);
    return routes[key](options);
  });
}

function requestsTo(method, path) {
  return global.fetch.mock.calls.filter(([url, options = {}]) =>
    (options.method || "GET") === method && new URL(url).pathname + new URL(url).search === path);
}

async function renderPage() {
  await act(async () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/projects"]}>
          <ProjectsPage />
        </MemoryRouter>
      </AuthProvider>
    );
  });
}

// A naive UTC time, as the backend sends it, `ms` before now.
function serverTimeAgo(ms) {
  return new Date(Date.now() - ms).toISOString().replace("Z", "");
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("token", "jwt-for-demo");
  localStorage.setItem("userEmail", "demo@example.com");
});

// --- loading, error, empty ----------------------------------------------------------------------

test("while projects load the page says so", async () => {
  mockFetch({ "GET /projects": () => new Promise(() => {}) });
  await renderPage();

  expect(screen.getByRole("status")).toHaveTextContent("Loading projects…");
});

test("a failed load shows the error, not the empty state, and retries", async () => {
  let reply = () => respond(500, { detail: "Internal server error. Please try again later." });
  mockFetch({ "GET /projects": () => reply() });
  await renderPage();

  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load your projects: Internal server error");
  expect(screen.queryByText("Create your first project")).toBeNull();

  reply = () => respond(200, [DL]);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Try again" })));
  expect(screen.getByRole("article", { name: "Project DL Unit 5" })).toBeInTheDocument();
});

test("with no projects the page suggests one per course", async () => {
  mockFetch({ "GET /projects": () => respond(200, []) });
  await renderPage();

  expect(screen.getByText("Create your first project")).toBeInTheDocument();
  expect(screen.getByText(/one per course/)).toBeInTheDocument();
});

// --- cards --------------------------------------------------------------------------------------

test("a card shows the name, description, counts and last activity", async () => {
  mockFetch({ "GET /projects": () => respond(200, [{ ...DL, last_activity: serverTimeAgo(2 * 3600 * 1000 + 60000) }]) });
  await renderPage();

  const card = screen.getByRole("article", { name: "Project DL Unit 5" });
  expect(within(card).getByText("RNNs and attention")).toBeInTheDocument();
  expect(within(card).getByText("2 files · 1 chat · Active 2 hours ago")).toBeInTheDocument();
  expect(within(card).queryByText("Archived")).toBeNull();
});

test("a project with neither files nor chats has no activity yet", async () => {
  mockFetch({ "GET /projects": () => respond(200, [BDA]) });
  await renderPage();

  expect(screen.getByText("0 files · 0 chats · No activity yet")).toBeInTheDocument();
});

test("archived projects are counted apart and listed only when expanded", async () => {
  mockFetch({ "GET /projects": () => respond(200, [DL, { ...BDA, archived: true }]) });
  await renderPage();

  expect(screen.getByText("Your projects (1)")).toBeInTheDocument();
  const toggle = screen.getByRole("button", { name: "Archived (1)" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("article", { name: "Project BDA" })).toBeNull();

  fireEvent.click(toggle);
  const card = screen.getByRole("article", { name: "Project BDA" });
  expect(within(card).getByText("Archived")).toBeInTheDocument();
  expect(within(card).getByRole("button", { name: /unarchive/i })).toBeInTheDocument();
});

test("when every project is archived the page says so", async () => {
  mockFetch({ "GET /projects": () => respond(200, [{ ...DL, archived: true }]) });
  await renderPage();

  expect(screen.getByText(/Every project is archived/)).toBeInTheDocument();
});

// --- create -------------------------------------------------------------------------------------

test("creating a project posts its trimmed name and description, then refreshes", async () => {
  let projects = [];
  let finish;
  mockFetch({
    "GET /projects": () => respond(200, projects),
    "POST /projects": () => new Promise((resolve) => { finish = resolve; }),
  });
  await renderPage();

  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "  BDA  " } });
  fireEvent.change(screen.getByLabelText(/^Description/), { target: { value: " Big data " } });
  fireEvent.click(screen.getByRole("button", { name: /create project/i }));

  expect(screen.getByRole("button", { name: /creating…/i })).toBeDisabled();
  expect(JSON.parse(requestsTo("POST", "/projects")[0][1].body)).toEqual({ name: "BDA", description: "Big data" });
  projects = [{ ...BDA, description: "Big data" }];
  await act(async () => finish({ ok: true, status: 201, json: () => Promise.resolve(projects[0]) }));

  expect(screen.getByText("Created project BDA.")).toBeInTheDocument();
  expect(screen.getByRole("article", { name: "Project BDA" })).toBeInTheDocument();
  expect(screen.getByLabelText(/^Name/)).toHaveValue("");
});

test("a project without a description sends only its name", async () => {
  mockFetch({ "GET /projects": () => respond(200, []), "POST /projects": () => respond(201, BDA) });
  await renderPage();

  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "BDA" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: /create project/i })));

  expect(JSON.parse(requestsTo("POST", "/projects")[0][1].body)).toEqual({ name: "BDA" });
});

test("an empty name is refused before any request", async () => {
  mockFetch({ "GET /projects": () => respond(200, []) });
  await renderPage();

  fireEvent.click(screen.getByRole("button", { name: /create project/i }));

  expect(screen.getByRole("alert")).toHaveTextContent("Give the project a name.");
  expect(requestsTo("POST", "/projects")).toHaveLength(0);
});

test("a duplicate name shows the server's message", async () => {
  mockFetch({
    "GET /projects": () => respond(200, [DL]),
    "POST /projects": () => respond(409, { detail: "You already have a project named “DL Unit 5”." }),
  });
  await renderPage();

  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "DL Unit 5" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: /create project/i })));

  expect(screen.getByRole("alert")).toHaveTextContent("You already have a project named");
});

// --- rename, archive, delete --------------------------------------------------------------------

test("renaming sends only the new name and reports it", async () => {
  mockFetch({
    "GET /projects": () => respond(200, [DL]),
    "PATCH /projects/3": () => respond(200, { ...DL, name: "DL Unit 6" }),
  });
  await renderPage();

  const card = screen.getByRole("article", { name: "Project DL Unit 5" });
  fireEvent.click(within(card).getByRole("button", { name: /rename/i }));
  fireEvent.change(within(card).getByLabelText("New name for DL Unit 5"), { target: { value: "DL Unit 6" } });
  await act(async () => fireEvent.click(within(card).getByRole("button", { name: "Save name" })));

  expect(JSON.parse(requestsTo("PATCH", "/projects/3")[0][1].body)).toEqual({ name: "DL Unit 6" });
  expect(screen.getByText("Renamed to DL Unit 6.")).toBeInTheDocument();
});

test("archiving sends the flag and says what it means", async () => {
  mockFetch({ "GET /projects": () => respond(200, [DL]), "PATCH /projects/3": () => respond(200, DL) });
  await renderPage();

  await act(async () => fireEvent.click(screen.getByRole("button", { name: /^archive$/i })));

  expect(JSON.parse(requestsTo("PATCH", "/projects/3")[0][1].body)).toEqual({ archived: true });
  expect(screen.getByText("Archived DL Unit 5: it takes no new files or chats.")).toBeInTheDocument();
});

test("deleting asks what happens to the files and sends that choice", async () => {
  mockFetch({
    "GET /projects": () => respond(200, [DL]),
    "DELETE /projects/3?documents=delete": () => respond(200, {
      status: "deleted", project_id: 3, documents: "delete", documents_deleted: 2,
      documents_unassigned: 0, chats_unassigned: 1, doc_version: 4,
    }),
  });
  await renderPage();

  fireEvent.click(screen.getByRole("button", { name: /delete$/i }));
  const dialog = screen.getByRole("dialog", { name: "Delete DL Unit 5" });
  expect(dialog).toHaveTextContent("1 chat will move to No project. What should happen to its 2 files?");
  const confirm = within(dialog).getByRole("button", { name: "Delete project" });
  expect(confirm).toBeDisabled(); // no default: the user must choose

  fireEvent.click(within(dialog).getByLabelText(/Delete them too/));
  await act(async () => fireEvent.click(confirm));

  expect(requestsTo("DELETE", "/projects/3?documents=delete")).toHaveLength(1);
  expect(screen.getByText("Deleted project DL Unit 5 and 2 files. Its 1 chat moved to No project.")).toBeInTheDocument();
});

test("a refused delete shows why on the card and keeps the project", async () => {
  mockFetch({
    "GET /projects": () => respond(200, [DL]),
    "DELETE /projects/3?documents=unassign": () => respond(409, {
      detail: "No project already has a file named notes.pdf. Rename or delete one of them first.",
    }),
  });
  await renderPage();

  fireEvent.click(screen.getByRole("button", { name: /delete$/i }));
  fireEvent.click(screen.getByLabelText(/Keep them/));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Delete project" })));

  const card = screen.getByRole("article", { name: "Project DL Unit 5" });
  expect(within(card).getByRole("alert")).toHaveTextContent("already has a file named notes.pdf");
});

// --- time helpers -------------------------------------------------------------------------------

test("server times without a zone are read as UTC", () => {
  expect(parseServerTime("2026-11-19T10:00:00").toISOString()).toBe("2026-11-19T10:00:00.000Z");
  expect(parseServerTime("2026-11-19T10:00:00+05:30").toISOString()).toBe("2026-11-19T04:30:00.000Z");
  expect(parseServerTime(null)).toBeNull();
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

test("older activity shows a date, and a project with chats but no messages its creation", () => {
  const now = new Date("2026-11-21T12:00:00Z");
  expect(lastActivityText({ ...DL, last_activity: "2026-11-01T12:00:00" }, now)).toBe("Active Nov 1");
  expect(lastActivityText({ ...DL, last_activity: null }, now)).toBe("Created Nov 19");
  expect(lastActivityText({ ...BDA, last_activity: null }, now)).toBe("No activity yet");
});
