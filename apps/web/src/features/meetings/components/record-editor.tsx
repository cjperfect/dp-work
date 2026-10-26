import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import "./record-editor.css";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import { withCollaboration } from "@blocknote/core/yjs";
import { zh } from "@blocknote/core/locales";
import type * as Y from "yjs";
import { collaboratorColor, renderCollaborationCursor } from "../lib/collaboration-cursor";
import type { RecordProvider } from "../lib/record-provider";

export function RecordEditor({
  doc,
  provider,
  editable,
  username,
}: {
  doc: Y.Doc;
  provider?: RecordProvider;
  editable: boolean;
  username: string;
}) {
  const collaboratorId = provider?.awareness.getLocalState()?.collaborator?.id;
  const identity = typeof collaboratorId === "number" ? collaboratorId : username;
  const editor = useCreateBlockNote(
    withCollaboration({
      dictionary: zh,
      collaboration: {
        fragment: doc.getXmlFragment("document"),
        provider,
        user: { name: username, color: collaboratorColor(identity) },
        renderCursor: renderCollaborationCursor,
        showCursorLabels: "always",
      },
    }),
    [doc, provider],
  );
  return <BlockNoteView editor={editor} theme="light" editable={editable} className="px-3 py-6" />;
}
