import { TextDecoder, TextEncoder } from "util";

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide.
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { fireEvent, render, screen, waitFor } = require("@testing-library/react");
const { MemoryRouter } = require("react-router-dom");
const CreateMapForm = require("./CreateMapForm").default;

const INDEXED = { id: 7, filename: "notes.pdf", chunks: 12 };
const NOT_SEARCHABLE = { id: 8, filename: "old-slides.pptx", chunks: 0 };

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function mockApi({ documents = () => respond(200, []), generate = () => respond(200, {}) }) {
  global.fetch = jest.fn((url) => {
    if (url.endsWith("/documents")) return documents();
    if (url.endsWith("/api/concepts/generate")) return generate();
    return respond(404, {});
  });
}

function renderForm() {
  return render(
    <MemoryRouter>
      <CreateMapForm onMapCreated={jest.fn()} onCancel={jest.fn()} />
    </MemoryRouter>
  );
}

function documentsCard() {
  return screen.getByRole("button", { name: /your documents/i });
}

async function submit(topic = "Photosynthesis") {
  fireEvent.change(screen.getByPlaceholderText(/neural networks/i), { target: { value: topic } });
  fireEvent.click(screen.getByRole("button", { name: /generate map/i }));
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("token", "jwt-for-demo");
});

test("with indexed documents the documents card is on by default and sent with the request", async () => {
  mockApi({ documents: () => respond(200, [INDEXED, NOT_SEARCHABLE]), generate: () => respond(200, { map_id: 1 }) });
  renderForm();
  expect(screen.getByText("Checking your documents…")).toBeInTheDocument();

  // Only the document with chunks counts.
  expect(await screen.findByText("Search your 1 indexed document")).toBeInTheDocument();
  expect(documentsCard()).toBeEnabled();
  expect(documentsCard()).toHaveAttribute("aria-pressed", "true");

  await submit();

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    expect.stringMatching(/\/api\/concepts\/generate$/), expect.anything()
  ));
  const [, options] = global.fetch.mock.calls.find(([url]) => url.endsWith("/api/concepts/generate"));
  expect(JSON.parse(options.body)).toMatchObject({ topic: "Photosynthesis", use_documents: true, use_web: true });
});

test("without indexed documents the card is disabled and points to the Documents page", async () => {
  mockApi({ documents: () => respond(200, [NOT_SEARCHABLE]) });
  renderForm();

  expect(await screen.findByText("No indexed documents yet")).toBeInTheDocument();
  expect(documentsCard()).toBeDisabled();
  expect(documentsCard()).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("link", { name: /upload a document first/i })).toHaveAttribute("href", "/documents");
});

test("if the documents can't be loaded the card says so and web search still works", async () => {
  mockApi({ documents: () => respond(500, { detail: "boom" }), generate: () => respond(200, { map_id: 1 }) });
  renderForm();

  expect(await screen.findByText("Couldn't load your documents")).toBeInTheDocument();
  expect(documentsCard()).toBeDisabled();

  await submit();
  await waitFor(() => {
    const call = global.fetch.mock.calls.find(([url]) => url.endsWith("/api/concepts/generate"));
    expect(JSON.parse(call[1].body)).toMatchObject({ use_documents: false, use_web: true });
  });
});

test.each([
  [422, "No passages in your documents match this topic. Try another topic or turn on web search."],
  [502, "Couldn't build a concept map from the passages found. Try again or rephrase the topic."],
])("a %i from generate shows the server's message in the error box", async (status, detail) => {
  mockApi({ documents: () => respond(200, [INDEXED]), generate: () => respond(status, { detail }) });
  renderForm();
  await screen.findByText("Search your 1 indexed document");

  await submit();

  expect(await screen.findByRole("alert")).toHaveTextContent(detail);
});

test("an error page that isn't JSON gets a generic message", async () => {
  mockApi({
    documents: () => respond(200, [INDEXED]),
    generate: () => Promise.resolve({ ok: false, status: 500, json: () => Promise.reject(new SyntaxError("not JSON")) }),
  });
  renderForm();
  await screen.findByText("Search your 1 indexed document");

  await submit();

  expect(await screen.findByRole("alert")).toHaveTextContent("Failed to generate concept map");
});
