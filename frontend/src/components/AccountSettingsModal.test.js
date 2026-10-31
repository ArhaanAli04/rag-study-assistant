import { TextDecoder, TextEncoder } from "util";

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide.
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { fireEvent, render, screen } = require("@testing-library/react");
const { MemoryRouter, Route, Routes } = require("react-router-dom");
const { AuthProvider } = require("../contexts/AuthContext");
const AccountSettingsModal = require("./AccountSettingsModal").default;
const LoginPage = require("../pages/LoginPage").default;

const DELETED = {
  documents: 2, sessions: 3, messages: 6, concept_maps: 0,
  failed_queries: 1, files_removed: 2, index_entries_removed: 14,
};

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function mockFetch(deleteResponse) {
  global.fetch = jest.fn((url, options = {}) => {
    if (options.method === "DELETE") return deleteResponse();
    if (url.endsWith("/user/stats")) return respond(200, { plan: "Free", documents_uploaded: 2, documents_limit: 10 });
    return respond(200, { name: "Demo", email: "demo@example.com" });
  });
}

function renderAt() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/settings" element={<AccountSettingsModal user={{ email: "demo@example.com" }} onClose={() => {}} />} />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  );
}

function confirmDelete() {
  fireEvent.click(screen.getByRole("button", { name: /delete account/i }));
  fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }));
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("token", "jwt-for-demo");
  localStorage.setItem("userEmail", "demo@example.com");
});

test("deleting the account logs out, clears the token and shows the summary on /login", async () => {
  mockFetch(() => respond(200, { message: "Account deleted successfully", deleted: DELETED }));
  renderAt();

  confirmDelete();

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Your account was deleted — 2 documents and 3 chats removed."
  );
  expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  expect(localStorage.getItem("token")).toBeNull();
  expect(localStorage.getItem("userEmail")).toBeNull();
});

test("a failed delete shows the server's message and keeps the user signed in", async () => {
  mockFetch(() => respond(500, { detail: "Internal server error. Please try again later." }));
  renderAt();

  confirmDelete();

  expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error. Please try again later.");
  expect(screen.getByRole("button", { name: /confirm delete/i })).toBeEnabled();
  expect(localStorage.getItem("token")).toBe("jwt-for-demo");
});

test("the confirm button is disabled while the request is in flight", async () => {
  let finish;
  mockFetch(() => new Promise((resolve) => { finish = resolve; }));
  renderAt();

  confirmDelete();

  expect(screen.getByRole("button", { name: /deleting/i })).toBeDisabled();
  finish({ ok: true, status: 200, json: () => Promise.resolve({ deleted: DELETED }) });
  expect(await screen.findByRole("status")).toBeInTheDocument();
});
