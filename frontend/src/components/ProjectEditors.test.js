import { act, fireEvent, render, screen } from "@testing-library/react";
import { DescriptionEditor, InstructionsEditor } from "./ProjectEditors";

const DL = { id: 3, name: "DL Unit 5", description: null, instructions: "Be brief." };

function respond(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

beforeEach(() => {
  localStorage.setItem("token", "jwt-for-demo");
  global.fetch = jest.fn(() => respond(200, DL));
});

test("the instructions editor marks unsaved changes until they are saved", async () => {
  const onSaved = jest.fn(() => Promise.resolve());
  render(<InstructionsEditor project={DL} onSaved={onSaved} />);

  expect(screen.queryByText("Unsaved changes")).toBeNull();
  fireEvent.change(screen.getByLabelText(/Instructions for every chat/), { target: { value: "Use bullets." } });
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save instructions" })));
  expect(screen.queryByText("Unsaved changes")).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("Saved");
  expect(onSaved).toHaveBeenCalled();
});

test("typing the saved text back clears the marker", () => {
  render(<InstructionsEditor project={DL} onSaved={jest.fn()} />);
  const box = screen.getByLabelText(/Instructions for every chat/);

  fireEvent.change(box, { target: { value: "Be brief. More." } });
  fireEvent.change(box, { target: { value: "Be brief." } });

  expect(screen.queryByText("Unsaved changes")).toBeNull();
});

test("a failed save keeps the text and the marker, and shows the error", async () => {
  global.fetch = jest.fn(() => respond(422, { detail: "String should have at most 4000 characters" }));
  render(<InstructionsEditor project={DL} onSaved={jest.fn()} />);

  fireEvent.change(screen.getByLabelText(/Instructions for every chat/), { target: { value: "Again." } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save instructions" })));

  expect(screen.getByRole("alert")).toHaveTextContent("at most 4000 characters");
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  expect(screen.getByLabelText(/Instructions for every chat/)).toHaveValue("Again.");
});

test("the description editor saves the description with its own limit", async () => {
  render(<DescriptionEditor project={DL} onSaved={jest.fn(() => Promise.resolve())} />);
  const box = screen.getByLabelText(/Description of DL Unit 5/);
  expect(box).toHaveAttribute("maxLength", "500");

  fireEvent.change(box, { target: { value: "RNNs" } });
  expect(screen.getByText("4 / 500")).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save description" })));

  const [, options] = global.fetch.mock.calls[0];
  expect(options.method).toBe("PATCH");
  expect(JSON.parse(options.body)).toEqual({ description: "RNNs" });
});
