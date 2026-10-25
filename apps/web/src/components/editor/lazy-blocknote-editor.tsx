import { lazy, Suspense } from "react";
import type { BlockNoteEditorProps } from "./blocknote-editor";

const Editor = lazy(() =>
  import("./blocknote-editor").then((module) => ({ default: module.BlockNoteEditor })),
);

export function LazyBlockNoteEditor(props: BlockNoteEditorProps) {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">正在加载富文本编辑器…</p>}>
      <Editor {...props} />
    </Suspense>
  );
}
