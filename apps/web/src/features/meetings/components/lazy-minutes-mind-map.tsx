import { lazy, Suspense, type ComponentProps } from "react";

const MindMap = lazy(() =>
  import("./minutes-mind-map").then((module) => ({ default: module.MinutesMindMap })),
);

export function LazyMinutesMindMap(props: ComponentProps<typeof MindMap>) {
  return (
    <Suspense fallback={<p className="p-4 text-sm text-muted-foreground">正在加载思维导图…</p>}>
      <MindMap {...props} />
    </Suspense>
  );
}
