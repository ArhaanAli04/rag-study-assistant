// The deletion summary has to outlive the page that receives it: logout() makes the route guard
// redirect to /login without any navigation state, so it travels through sessionStorage instead.
export const ACCOUNT_DELETED_KEY = "accountDeletedSummary";

export function rememberAccountDeletion(summary) {
  try {
    sessionStorage.setItem(ACCOUNT_DELETED_KEY, JSON.stringify(summary || {}));
  } catch (error) {
    // Storage can be unavailable (private mode, quota); the account is deleted either way.
    console.warn("Could not store the account deletion summary", error);
  }
}

export function readAccountDeletion() {
  try {
    const raw = sessionStorage.getItem(ACCOUNT_DELETED_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.warn("Could not read the account deletion summary", error);
    return null;
  }
}

export function forgetAccountDeletion() {
  try {
    sessionStorage.removeItem(ACCOUNT_DELETED_KEY);
  } catch (error) {
    console.warn("Could not clear the account deletion summary", error);
  }
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export function accountDeletedNotice(deleted) {
  if (!deleted) return "";
  const documents = deleted.documents ?? 0;
  const chats = deleted.sessions ?? 0;
  return `Your account was deleted — ${plural(documents, "document")} and ${plural(chats, "chat")} removed.`;
}
