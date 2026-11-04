import type { Meeting } from "@/interfaces/meeting";
import { createStateSubscription } from "./state-events";

export const subscribeGenerationEvents = createStateSubscription<Meeting>({
  path: "/api/meetings/events",
  snapshotType: "meetings.snapshot",
  snapshotKey: "meetings",
  updateType: "meeting.updated",
  updateKey: "meeting",
  removedType: "meeting.removed",
  removedKey: "meeting_id",
  isStale: (previous, next) => (previous?.revision ?? 0) > next.revision,
});
