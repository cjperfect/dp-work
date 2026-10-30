import type { RecordDocument } from "@/interfaces/meeting";
import { useEffect, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { useAuthStore } from "@/stores/auth";
import { resolveRecordShare } from "@/apis/meeting-records";

import { RecordWorkspace } from "./record-workspace";
import { buttonVariants } from "@/components/ui/button";

export function SharedRecordPage() {
  const { token } = useParams({ from: "/shared/meeting-records/$token" });
  const userId = useAuthStore((state) => state.user?.id);
  const [document, setDocument] = useState<RecordDocument | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!userId) return;
    let alive = true;
    void (async () => {
      try {
        const value = await resolveRecordShare(token);
        if (alive) {
          setDocument(value);
          setError("");
        }
      } catch (cause) {
        if (alive) setError(cause instanceof Error ? cause.message : "");
      }
    })();
    return () => {
      alive = false;
    };
  }, [token, userId]);
  if (!userId)
    return (
      <main className="m-auto flex max-w-lg flex-col gap-5 p-12">
        <h1 className="text-xl font-semibold">登录后协同编辑会议纪要</h1>
        <Link
          to="/sign-in"
          search={{ redirect: `/shared/meeting-records/${token}` }}
          className={buttonVariants()}
        >
          前往登录
        </Link>
      </main>
    );
  return (
    <main className="flex h-dvh flex-col gap-4 p-6">
      <header>
        <p className="text-xs text-muted-foreground">会议纪要 · 协同编辑</p>
        <h1 className="mt-2 text-xl font-semibold">{document?.title ?? "分享的会议"}</h1>
        <p className="mt-2 text-xs text-muted-foreground">恢复版本与归档由会议创建者操作。</p>
      </header>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {document && (
        <section className="flex min-h-0 flex-1 flex-col rounded-xl border">
          <RecordWorkspace
            key={`${userId}:${token}`}
            meetingId={document.meeting_id}
            shareToken={token}
            initial={document}
          />
        </section>
      )}
    </main>
  );
}
