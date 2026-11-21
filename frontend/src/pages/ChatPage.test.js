// ChatPage keeps the open chat in the URL (Day 19). The window and sidebar are stubbed: these tests
// are about which chat the URL opens, not about chatting.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider } from "../contexts/AuthContext";
import ChatPage from "./ChatPage";

jest.mock("../components/TopNav", () => () => null);
jest.mock("../components/ChatWindow", () => (props) => (
  <div data-testid="chat-window" data-session={String(props.sessionId)} data-project={String(props.initialProjectId)}>
    <button onClick={() => props.onSessionCreated(42)}>finish first answer</button>
  </div>
));
jest.mock("../components/SessionSidebar", () => (props) => (
  <div>
    <button onClick={() => props.onSelectSession(5)}>open chat 5</button>
    <button onClick={props.onNewChat}>new chat</button>
  </div>
));

function CurrentUrl() {
  const location = useLocation();
  return <output data-testid="url">{location.pathname + location.search}</output>;
}

async function renderAt(url) {
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }));
  await act(async () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/chat" element={<><ChatPage /><CurrentUrl /></>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );
  });
}

const chatWindow = () => screen.getByTestId("chat-window");

beforeEach(() => {
  localStorage.setItem("token", "jwt-for-demo");
});

test("/chat?project=3 opens a new chat preselected to project 3", async () => {
  await renderAt("/chat?project=3");

  expect(chatWindow()).toHaveAttribute("data-session", "null");
  expect(chatWindow()).toHaveAttribute("data-project", "3");
});

test("once the new chat exists the URL names it, so a refresh reopens it", async () => {
  await renderAt("/chat?project=3");

  await act(async () => fireEvent.click(screen.getByRole("button", { name: "finish first answer" })));

  expect(screen.getByTestId("url")).toHaveTextContent("/chat?session=42");
  expect(chatWindow()).toHaveAttribute("data-session", "42");
  expect(chatWindow()).toHaveAttribute("data-project", "null");
});

test("/chat?session=42 opens that chat and ignores a project", async () => {
  await renderAt("/chat?session=42&project=3");

  expect(chatWindow()).toHaveAttribute("data-session", "42");
  expect(chatWindow()).toHaveAttribute("data-project", "null");
});

test("the sidebar writes the open chat into the URL, and New chat clears it", async () => {
  await renderAt("/chat");

  fireEvent.click(screen.getByRole("button", { name: "open chat 5" }));
  expect(screen.getByTestId("url")).toHaveTextContent("/chat?session=5");
  expect(chatWindow()).toHaveAttribute("data-session", "5");

  fireEvent.click(screen.getByRole("button", { name: "new chat" }));
  expect(screen.getByTestId("url").textContent).toBe("/chat");
  expect(chatWindow()).toHaveAttribute("data-session", "null");
});

test("non-numeric ids in the URL are ignored", async () => {
  await renderAt("/chat?session=abc&project=x");

  expect(chatWindow()).toHaveAttribute("data-session", "null");
  expect(chatWindow()).toHaveAttribute("data-project", "null");
});
