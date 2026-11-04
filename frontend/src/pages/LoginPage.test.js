import { TextDecoder, TextEncoder } from "util";

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide.
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { fireEvent, render, screen } = require("@testing-library/react");
const { MemoryRouter } = require("react-router-dom");
const { AuthProvider } = require("../contexts/AuthContext");
const { AppRoutes } = require("../App");

jest.mock("react-markdown", () => ({ children }) => <div>{children}</div>);
jest.mock("remark-gfm", () => () => {});
jest.mock("../utils/exportUtils", () => ({
  exportChatAsMarkdown: jest.fn(),
  exportChatAsPDF: jest.fn(),
}));

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function renderApp(path) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>
  );
}

function signIn(email, password) {
  fireEvent.change(screen.getByPlaceholderText("you@example.com"), { target: { value: email } });
  fireEvent.change(screen.getByPlaceholderText("••••••••"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  // LoginPage logs each attempt; keep the test output readable.
  jest.spyOn(console, "log").mockImplementation(() => {});
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("an anonymous visitor to a protected page lands on the login form", async () => {
  global.fetch = jest.fn(() => respond(401, { detail: "Not authenticated" }));
  renderApp("/chat");

  expect(await screen.findByRole("button", { name: /sign in/i })).toBeInTheDocument();
  expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("signing in posts the credentials as a form, stores the token and opens the chat", async () => {
  global.fetch = jest.fn((url) => {
    if (url.endsWith("/login")) return respond(200, { access_token: "jwt-from-login", token_type: "bearer" });
    if (url.includes("/sessions")) return respond(200, []);
    if (url.endsWith("/user/stats")) return respond(200, { plan: "Free", documents_uploaded: 0, documents_limit: 10 });
    return respond(200, { name: "Demo User", email: "demo@example.com" });
  });
  renderApp("/login");

  signIn("demo@example.com", "correct-horse-1");

  expect(await screen.findByPlaceholderText("Ask me anything...")).toBeInTheDocument();
  expect(localStorage.getItem("token")).toBe("jwt-from-login");
  const [url, options] = global.fetch.mock.calls.find(([u]) => u.endsWith("/login"));
  expect(url).toMatch(/\/login$/);
  expect(options.method).toBe("POST");
  expect(options.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
  expect(new URLSearchParams(options.body).get("username")).toBe("demo@example.com");
  expect(new URLSearchParams(options.body).get("password")).toBe("correct-horse-1");
});

test("a wrong password shows the server's message and stays on the form", async () => {
  global.fetch = jest.fn(() => respond(401, { detail: "Invalid credentials" }));
  renderApp("/login");

  signIn("demo@example.com", "wrong-password");

  expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /sign in/i })).toBeEnabled();
  expect(localStorage.getItem("token")).toBeNull();
});
