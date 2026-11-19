import { accountDeletedNotice } from "./accountDeletion";

test.each([
  [{ documents: 1, sessions: 2 }, "Your account was deleted — 1 document and 2 chats removed."],
  [{ documents: 1, sessions: 2, projects: 0 }, "Your account was deleted — 1 document and 2 chats removed."],
  [{ documents: 2, sessions: 3, projects: 1 }, "Your account was deleted — 2 documents, 3 chats and 1 project removed."],
  [{ documents: 0, sessions: 1, projects: 4 }, "Your account was deleted — 0 documents, 1 chat and 4 projects removed."],
])("account deletion notice for %o", (deleted, expected) => {
  expect(accountDeletedNotice(deleted)).toBe(expected);
});
