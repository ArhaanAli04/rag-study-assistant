import { act, fireEvent, render, screen } from "@testing-library/react";
import SessionProjectModal from "./SessionProjectModal";

const SESSION = { id: 42, title: "LSTM gates", project_id: null, project_name: null };
const PROJECTS = [
  { id: 3, name: "DL Unit 5", archived: false },
  { id: 4, name: "Old course", archived: true },
];

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function mockFetch({ projects = () => respond(200, PROJECTS), move = () => respond(200, { status: "moved" }) } = {}) {
  global.fetch = jest.fn((url, options = {}) => {
    const { pathname } = new URL(url);
    if (pathname === "/projects") return projects();
    if (options.method === "PATCH" && pathname === "/sessions/42/project") return move(options);
    throw new Error(`unexpected request ${pathname}`);
  });
}

function renderModal(session = SESSION) {
  const onClose = jest.fn();
  const onMoved = jest.fn(() => Promise.resolve());
  render(<SessionProjectModal session={session} onClose={onClose} onMoved={onMoved} />);
  return { onClose, onMoved };
}

test("it loads the projects, offering only active ones", async () => {
  mockFetch();
  renderModal();

  expect(screen.getByRole("status")).toHaveTextContent("Loading projects…");
  const picker = await screen.findByLabelText("Project");
  expect(Array.from(picker.options).map((o) => o.textContent)).toEqual(["No project", "DL Unit 5"]);
  expect(screen.getByRole("button", { name: "Move chat" })).toBeDisabled(); // nothing changed yet
});

test("moving sends the project, refreshes the sidebar and closes", async () => {
  mockFetch();
  const { onClose, onMoved } = renderModal();

  fireEvent.change(await screen.findByLabelText("Project"), { target: { value: "3" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Move chat" })));

  const [, options] = global.fetch.mock.calls.find(([, o = {}]) => o.method === "PATCH");
  expect(JSON.parse(options.body)).toEqual({ project_id: 3 });
  expect(onMoved).toHaveBeenCalled();
  expect(onClose).toHaveBeenCalled();
});

test("a chat in a project can move back to No project", async () => {
  mockFetch();
  renderModal({ ...SESSION, project_id: 3, project_name: "DL Unit 5" });

  fireEvent.change(await screen.findByLabelText("Project"), { target: { value: "" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Move chat" })));

  const [, options] = global.fetch.mock.calls.find(([, o = {}]) => o.method === "PATCH");
  expect(JSON.parse(options.body)).toEqual({ project_id: null });
});

test("a refused move shows why and stays open", async () => {
  mockFetch({ move: () => respond(409, { detail: "This project is archived. Unarchive it to add files or start chats." }) });
  const { onClose, onMoved } = renderModal();

  fireEvent.change(await screen.findByLabelText("Project"), { target: { value: "3" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Move chat" })));

  expect(screen.getByRole("alert")).toHaveTextContent("This project is archived.");
  expect(onMoved).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
});

test("with no projects it explains where to create one", async () => {
  mockFetch({ projects: () => respond(200, []) });
  renderModal();

  expect(await screen.findByText(/No projects yet. Create one on the Documents page/)).toBeInTheDocument();
});

test("a failed load says so", async () => {
  mockFetch({ projects: () => respond(500, { detail: "Internal server error." }) });
  renderModal();

  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your projects: Internal server error.");
});
