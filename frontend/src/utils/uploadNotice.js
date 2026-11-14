// What to tell the user after an upload, from POST /upload's `status` (Day 15, I6). An identical
// re-upload is no longer re-indexed, so the page must say so instead of looking like nothing happened.
const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

export function uploadNotice(result) {
  const name = result.filename || "The file";
  const chunks = result.chunks_indexed ?? 0;
  switch (result.status) {
    case "unchanged":
      return `${name} is already indexed — nothing changed, so nothing was re-indexed.`;
    case "changed":
      return `Version ${result.version} of ${name} indexed (${plural(chunks, "passage")}). The previous version is no longer searched.`;
    case "reindexed":
      return `${name} is searchable again — indexed ${plural(chunks, "passage")}.`;
    default:
      if (chunks === 0) {
        return `${name} was saved, but no text was found in it to search.`;
      }
      return `Indexed ${plural(chunks, "passage")} from ${name}. You can ask about it now.`;
  }
}

// DELETE /documents/{id} removes every version of the file name (Day 15, I5).
export function deleteNotice(fileName, versionsDeleted = 1) {
  const versions = versionsDeleted > 1 ? ` (all ${versionsDeleted} versions)` : "";
  return `Deleted ${fileName || "the document"}${versions}. New answers won't cite it.`;
}
