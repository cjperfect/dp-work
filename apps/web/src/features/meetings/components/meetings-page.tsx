import type { Meeting } from "@/interfaces/meeting";
import { useEffect, useRef, useState } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import { Clock3, FileText, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardFooter } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { trackGenerations, forgetGeneration } from "@/stores/meeting/meeting-generation";
import { useAuthStore } from "@/stores/auth";
import { useGenerationEvents } from "../hooks/use-generation-events";
import { MeetingCreateDialog } from "./meeting-create-dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { meetingCategory, generationStatus } from "../lib/minutes-state";
import { STATUS_LABELS } from "@/apis/meetings";

import { useMeetingCache } from "@/stores/meeting";
import { listSavedMeetings, removeDraft } from "../lib/workspace-storage";

type Category = "pending" | "archived";
const CATEGORIES: { key: Category; label: string }[] = [
  { key: "pending", label: "待生成" },
  { key: "archived", label: "已归档" },
];

export function MeetingsPage() {
  const { view } = useSearch({ from: "/_app/meetings/" });
  const accountId = useAuthStore((s) => s.user?.id);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<Category>(view ?? "pending");
  const [create, setCreate] = useState(false);
  const [revision, setRevision] = useState(0);
  const [deleting, setDeleting] = useState<Meeting | null>(null);
  const [busy, setBusy] = useState(false);
  const actionLock = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    if (!accountId) return;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const rows = await listSavedMeetings(accountId);
        if (alive) {
          trackGenerations(rows);
          setMeetings(rows);
        }
      } catch (cause) {
        if (alive) setError(cause instanceof Error ? cause.message : "无法加载会议");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [accountId, revision]);
  useGenerationEvents(
    meetings.some((row) => generationStatus(row) === "generating"),
    (updates, snapshot) => {
      setMeetings((current) =>
        snapshot
          ? updates
          : current.map(
              (row) =>
                updates.find((next) => next.id === row.id && next.revision >= row.revision) ?? row,
            ),
      );
    },
  );
  const rows = meetings.filter((row) =>
    `${row.title} ${row.participants.join(" ")}`
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );
  function inCategory(row: Meeting, category: Category) {
    return meetingCategory(row) === category;
  }
  const categoryRows = rows.filter((row) => inCategory(row, category));
  const counts = {
    pending: rows.filter((row) => inCategory(row, "pending")).length,
    archived: rows.filter((row) => inCategory(row, "archived")).length,
  };
  async function remove() {
    if (!deleting || !accountId || actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setActionError(null);
    try {
      await removeDraft(accountId, deleting.id);
      forgetGeneration(deleting.id);
      useMeetingCache.setState((state) => {
        const records = { ...state.records };
        delete records[`${accountId}:${deleting.id}`];
        return { records };
      });
      setDeleting(null);
      setRevision((r) => r + 1);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "删除失败");
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto px-6 py-8 md:px-10">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs tracking-[.18em] text-muted-foreground">MEETING NOTES</p>
          <h1 className="text-2xl font-semibold tracking-tight">会议</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            记录讨论，整理共识，让每一次会议都有所沉淀。
          </p>
        </div>
        <Button onClick={() => setCreate(true)}>
          <Plus className="size-4" />
          开始会议
        </Button>
      </header>
      <div className="mt-8 flex flex-wrap gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            className="pl-9"
            aria-label="搜索会议"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索会议或参会人"
          />
        </div>
      </div>
      <Tabs
        value={category}
        onValueChange={(value) => setCategory(value as Category)}
        className="mt-6"
      >
        <TabsList>
          {CATEGORIES.map((item) => (
            <TabsTrigger key={item.key} value={item.key}>
              {item.label}
              {counts[item.key] > 0 && (
                <span className="ml-1 rounded-full bg-background px-1.5 text-xs tabular-nums">
                  {counts[item.key]}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={category} className="mt-4">
          {error && (
            <div role="alert" className="mb-4 rounded-lg border border-destructive/30 p-3 text-sm">
              {error}
              <Button variant="ghost" size="sm" onClick={() => setRevision((r) => r + 1)}>
                重试
              </Button>
            </div>
          )}
          <div className="my-4 text-xs text-muted-foreground">
            {loading ? "正在读取会议…" : `${categoryRows.length} 场会议`}
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-4">
            {categoryRows.map((row) => (
              <Card
                key={row.id}
                role="article"
                aria-labelledby={`meeting-title-${row.id}`}
                className="min-h-56 min-w-0 gap-4 px-5 py-5 shadow-none transition-shadow hover:shadow-sm"
              >
                <Link
                  className="flex min-w-0 flex-1 flex-col rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  to={
                    row.status === "active" || row.status === "paused"
                      ? "/meetings/active"
                      : "/meetings/minutes"
                  }
                  search={{ id: row.id }}
                >
                  <span
                    className="mb-4 grid size-10 place-items-center rounded-xl bg-muted text-muted-foreground"
                    aria-hidden="true"
                  >
                    <FileText className="size-5" />
                  </span>
                  <h2
                    id={`meeting-title-${row.id}`}
                    title={row.title}
                    className="mb-3 line-clamp-2 min-h-12 break-words text-sm font-semibold leading-6"
                  >
                    {row.title}
                  </h2>
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${generationStatus(row) === "generating" ? "bg-blue-50 text-blue-700" : row.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-muted text-muted-foreground"}`}
                    >
                      {row.status === "archived"
                        ? "已归档"
                        : generationStatus(row) === "failed"
                          ? "生成失败"
                          : generationStatus(row) === "generating"
                            ? "生成中"
                            : generationStatus(row) === "ready"
                              ? "已生成"
                              : STATUS_LABELS[row.status]}
                    </span>
                  </div>
                  <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Clock3 className="size-3" />
                    {new Date(row.scheduled_at).toLocaleString("zh-CN")}
                    {row.participants.length > 0 && ` · ${row.participants.join("、")}`}
                  </p>
                </Link>
                <CardFooter className="mt-auto gap-2 border-t px-0 pt-4">
                  <Button
                    size="sm"
                    variant="outline"
                    nativeButton={false}
                    render={
                      <Link
                        to={
                          row.status === "active" || row.status === "paused"
                            ? "/meetings/active"
                            : "/meetings/minutes"
                        }
                        search={{ id: row.id }}
                      />
                    }
                  >
                    <FileText className="size-4" />
                    查看
                  </Button>
                  <Popover
                    open={deleting?.id === row.id}
                    onOpenChange={(open) => {
                      if (busy) return;
                      setDeleting(open ? row : null);
                      setActionError(null);
                    }}
                  >
                    <PopoverTrigger
                      render={
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          disabled={busy}
                          aria-label={`删除会议 ${row.title}`}
                          className="ml-auto text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      }
                    />
                    <PopoverContent
                      align="end"
                      className="w-72 max-w-[calc(100vw-2rem)] p-3"
                      aria-labelledby={`delete-meeting-${row.id}`}
                    >
                      <h2
                        id={`delete-meeting-${row.id}`}
                        className="break-words text-sm font-medium"
                      >
                        删除「{row.title}」？
                      </h2>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        将删除会议、转写记录和纪要草稿，已归档的知识库文档保留。
                      </p>
                      {actionError && (
                        <p role="alert" className="mt-2 text-xs text-destructive">
                          {actionError}
                        </p>
                      )}
                      <div className="mt-3 flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => setDeleting(null)}
                        >
                          取消
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={busy}
                          onClick={() => void remove()}
                        >
                          {busy ? "删除中…" : "确认删除"}
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                </CardFooter>
              </Card>
            ))}
          </div>
          {!loading && !categoryRows.length && (
            <div className="mt-8 flex flex-col items-center rounded-xl border border-dashed p-12 text-center">
              <FileText className="mb-4 size-8 text-muted-foreground" />
              <p className="font-medium">
                {rows.length ? "没有找到符合条件的会议" : "从第一场会议开始"}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                会议内容由 ASR 自动转写，结束后可提交生成会议纪要。
              </p>
            </div>
          )}
        </TabsContent>
      </Tabs>
      <MeetingCreateDialog open={create} onOpenChange={setCreate} />
      {actionError && !deleting && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {actionError}
        </p>
      )}
    </div>
  );
}
