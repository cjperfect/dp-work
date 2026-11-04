import type { DocumentParseState } from "@/interfaces/knowledge";
import { createStateSubscription } from "../state-events";

export const subscribeDocumentParseEvents = createStateSubscription<DocumentParseState>({
  path: "/api/knowledge-bases/events",
  snapshotType: "documents.snapshot",
  snapshotKey: "documents",
  updateType: "document.updated",
  updateKey: "document",
});
