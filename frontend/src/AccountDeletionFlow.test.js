import { TextDecoder, TextEncoder } from "util";

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide.
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { fireEvent, render, screen } = require("@testing-library/react");
const { MemoryRouter } = require("react-router-dom");
const { AuthProvider } = require("./contexts/AuthContext");
const { AppRoutes } = require("./App");

jest.mock("react-markdown", () => ({ children }) => <div>{children}</div>);
jest.mock("remark-gfm", () => () => {});
jest.mock("./utils/exportUtils", () => ({
  exportChatAsMarkdown: jest.fn(),
  exportChatAsPDF: jest.fn(),
}));

const DELETED = {
  documents: 1, sessions: 2, messages: 4, concept_maps: 0,
  failed_queries: 0, files_removed: 1, index_entries_removed: 6,
};

function respond(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("token", "jwt-for-demo");
  global.fetch = jest.fn((url, options = {}) => {
    if (options.method === "DELETE") return respond({ message: "Account deleted successfully", deleted: DELETED });
    if (url.includes("/sessions")) return respond([]);
    if (url.endsWith("/user/stats")) return respond({ plan: "Free", documents_uploaded: 1, documents_limit: 10 });
    return respond({ name: "Demo User", email: "demo@example.com" });
  });
});

test("deleting the account from a protected page lands on /login with the summary notice", async () => {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/chat"]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>
  );

  fireEvent.click(await screen.findByTitle("Demo User"));
  fireEvent.click(screen.getByText("Account Settings"));
  fireEvent.click(await screen.findByRole("button", { name: /delete account/i }));
  fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }));

  expect(await screen.findByRole("button", { name: /sign in/i })).toBeInTheDocument();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Your account was deleted — 1 document and 2 chats removed."
  );
  expect(localStorage.getItem("token")).toBeNull();
  // Read once: a reload of /login must not show the notice again.
  expect(sessionStorage.getItem("accountDeletedSummary")).toBeNull();
});
