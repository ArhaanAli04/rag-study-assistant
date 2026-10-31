import { render, screen } from "@testing-library/react";
import MessageList from "./MessageList";

// react-markdown and remark-gfm are ESM-only, which CRA's Jest doesn't transform.
jest.mock("react-markdown", () => ({ children }) => <div>{children}</div>);
jest.mock("remark-gfm", () => () => {});

const REFUSAL = "I can't follow requests to ignore or reveal my instructions.";

function renderMessages(messages) {
  return render(
    <MessageList
      messages={messages}
      streamingAnswer=""
      onFeedback={jest.fn()}
      showCommentFor={null}
      feedbackComment=""
      onCommentChange={jest.fn()}
      onCancelComment={jest.fn()}
    />
  );
}

beforeEach(() => {
  // MessageList fetches the user profile on mount; a failed fetch keeps the default avatar.
  global.fetch = jest.fn(() => Promise.resolve({ ok: false }));
});

test("a refusal shows its text and the copy button, but no thumbs up/down", async () => {
  renderMessages([{ role: "assistant", content: REFUSAL, id: 1, sources: [], isRefusal: true }]);

  expect(await screen.findByText(REFUSAL)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy response" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Helpful" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Not helpful" })).not.toBeInTheDocument();
});

test("a normal answer still shows thumbs up/down", async () => {
  renderMessages([{ role: "assistant", content: "Gradient descent is...", id: 23, sources: [] }]);

  expect(await screen.findByRole("button", { name: "Helpful" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Not helpful" })).toBeInTheDocument();
});
