import { localAccountId } from "@/features/auth/lib/auth";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { debounce } from "es-toolkit/function";
import { Link } from "@tanstack/react-router";
import { BookOpen, FileText, Loader2, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/pagination";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuthStore } from "@/stores/auth";
import { useKnowledgeBasePage } from "@/features/knowledge/hooks/use-knowledge-base-page";
import { createKnowledgeBase, deleteKnowledgeBase, updateKnowledgeBase } from "@/stores/knowledge";
import type { StoredKnowledgeBase } from "../lib/knowledge-repository";
import { getKbFiles } from "@/stores/knowledge-upload";

export function KnowledgePage() {
  const user = useAuthStore((state) => state.user);
  const accountId = localAccountId(user);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [query, setQuery] = useState("");
  const applySearch = useMemo(
    () =>
      debounce((value: string) => {
        setQuery(value.trim());
        setPage(1);
      }, 300),
    [],
  );
  useEffect(() => () => applySearch.cancel(), [applySearch]);
  const { result, loading, error, reload } = useKnowledgeBasePage(query, page, pageSize, setPage);
  const bases = result?.item ?? [];
  const changeSearch = (value: string) => {
    setSearch(value);
    if (value.trim()) applySearch(value);
    else {
      applySearch.cancel();
      setQuery("");
      setPage(1);
    }
  };
  const [form, setForm] = useState<{ base?: StoredKnowledgeBase } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<StoredKnowledgeBase | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const deletingRef = useRef(false);

  async function confirmDelete() {
    if (!user || !accountId || !deleteTarget || deletingRef.current) return;
    deletingRef.current = true;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteKnowledgeBase(accountId, deleteTarget.id);
      reload();
      setNotice(`已删除「${deleteTarget.name}」`);
      setDeleteTarget(null);
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "删除失败，请重试。");
    } finally {
      deletingRef.current = false;
      setDeleting(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto px-6 py-8 md:px-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">知识库</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            把文档和经验整理在一起，建立自己的知识空间。
          </p>
        </div>
        <Button disabled={loading || !!error} onClick={() => setForm({})}>
          <Plus className="size-4" />
          新建知识库
        </Button>
      </header>

      <div className="mt-7 flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:max-w-sm">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(event) => changeSearch(event.target.value)}
            aria-label="搜索知识库"
            placeholder="搜索名称或描述"
            className="h-10 pl-9 pr-9"
          />
          {search && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="清空搜索"
              className="absolute right-1 top-1/2 -translate-y-1/2"
              onClick={() => changeSearch("")}
            >
              <X className="size-3.5" />
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {result ? (query ? `匹配 ${result.total} 个知识库` : `共 ${result.total} 个知识库`) : ""}
        </p>
      </div>
      {notice && (
        <p role="status" className="mt-4 text-xs text-emerald-700">
          {notice}
        </p>
      )}

      {error ? (
        <div role="alert" className="mt-6 rounded-xl border border-destructive/20 p-6">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={reload}>
            重新加载
          </Button>
        </div>
      ) : loading ? (
        <div
          role="status"
          className="flex min-h-56 items-center justify-center gap-2 text-sm text-muted-foreground"
        >
          <Loader2 className="size-4 animate-spin" />
          正在读取知识库…
        </div>
      ) : bases.length ? (
        <ul className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {bases.map((base) => (
            <li
              key={base.id}
              className="group flex min-w-0 flex-col rounded-xl border bg-card p-5 transition-shadow hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <span className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                  <BookOpen className="size-5" />
                </span>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`编辑知识库 ${base.name}`}
                    onClick={() => setForm({ base })}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Popover
                    open={deleteTarget?.id === base.id}
                    onOpenChange={(open) => {
                      if (open) {
                        setDeleteError(null);
                        setDeleteTarget(base);
                      } else if (!deleting) {
                        setDeleteTarget(null);
                      }
                    }}
                  >
                    <PopoverTrigger
                      render={
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`删除知识库 ${base.name}`}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      }
                    />
                    <PopoverContent
                      align="end"
                      className="w-72 max-w-[calc(100vw-2rem)] p-3"
                      aria-labelledby={`delete-kb-title-${base.id}`}
                      aria-describedby={`delete-kb-description-${base.id}`}
                      aria-busy={deleting}
                    >
                      <h2 id={`delete-kb-title-${base.id}`} className="text-sm font-medium">
                        删除知识库？
                      </h2>
                      <p
                        id={`delete-kb-description-${base.id}`}
                        className="text-muted-foreground mt-1 break-words text-xs"
                      >
                        删除「{base.name}」后，将无法再访问其中的文档。此操作无法撤销。
                      </p>
                      {deleteError && (
                        <p role="alert" className="mt-2 text-xs text-destructive">
                          {deleteError}
                        </p>
                      )}
                      <div className="mt-3 flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={deleting}
                          onClick={() => setDeleteTarget(null)}
                        >
                          取消
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={deleting}
                          onClick={() => void confirmDelete()}
                        >
                          {deleting && <Loader2 className="size-4 animate-spin" />}
                          {deleting ? "正在删除…" : "确认删除"}
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              </div>
              <Link
                to="/knowledge/$kbId"
                params={{ kbId: base.id }}
                className="mt-4 break-words text-sm font-semibold outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
              >
                {base.name}
              </Link>
              <p className="mt-1.5 line-clamp-2 min-h-10 break-words text-xs leading-5 text-muted-foreground">
                {base.description || "暂无描述"}
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <FileText className="size-3.5" />
                  {getKbFiles(base.id).length + (base.documentCount ?? 0)} 个文件
                </span>
                <span>
                  更新于{" "}
                  {new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(
                    new Date(base.updatedAt),
                  )}
                </span>
                <span className="ml-auto max-w-24 truncate">{base.owner}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <section className="mt-5 flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed px-6 text-center">
          <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <BookOpen className="size-6" />
          </span>
          <h2 className="text-sm font-medium">
            {query ? "没有找到匹配的知识库" : "从你的第一个知识库开始"}
          </h2>
          <p className="mt-2 max-w-sm text-xs leading-5 text-muted-foreground">
            {query
              ? "试试其他名称，或用描述中的关键词搜索。"
              : "按项目、部门或主题归纳资料，让积累的知识有处可放。"}
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-5"
            onClick={() => (query ? changeSearch("") : setForm({}))}
          >
            {query ? "清空搜索" : "新建知识库"}
          </Button>
        </section>
      )}
      {result && !loading && !error && (
        <Pagination
          className="mt-6"
          page={page}
          pageSize={pageSize}
          total={result.total}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      )}
      <p className="mt-6 text-xs leading-5 text-muted-foreground">
        知识库新增、查询、编辑和删除已接入服务器；文档操作暂使用本地模拟数据。
      </p>

      {form && (
        <KnowledgeBaseForm
          base={form.base}
          onClose={() => setForm(null)}
          onSaved={(name) => {
            setNotice(`已${form.base ? "更新" : "创建"}「${name}」`);
            setForm(null);
            if (!form.base && page !== 1) setPage(1);
            else reload();
          }}
        />
      )}
    </div>
  );
}

function KnowledgeBaseForm({
  base,
  onClose,
  onSaved,
}: {
  base?: StoredKnowledgeBase;
  onClose: () => void;
  onSaved: (name: string) => void;
}) {
  const user = useAuthStore((state) => state.user);
  const accountId = localAccountId(user);
  const [name, setName] = useState(base?.name ?? "");
  const [description, setDescription] = useState(base?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const nameRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (savingRef.current || !user || !accountId) return;
    if (!name.trim()) {
      setError("请输入知识库名称。");
      nameRef.current?.focus();
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const input = { name, description };
      if (base) await updateKnowledgeBase(accountId, base.id, input);
      else await createKnowledgeBase(accountId, input);
      onSaved(name.trim());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，请重试。");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md" showCloseButton={!saving}>
        <DialogHeader>
          <DialogTitle>{base ? "编辑知识库" : "新建知识库"}</DialogTitle>
          <DialogDescription>用清晰的名称和描述，说明这里收录的资料。</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate aria-busy={saving} className="grid gap-4">
          <div className="grid gap-2">
            <label htmlFor="kb-name" className="text-sm font-medium">
              名称 <span className="text-destructive">*</span>
            </label>
            <Input
              ref={nameRef}
              id="kb-name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setError(null);
              }}
              placeholder="例如：产品设计规范"
              disabled={saving}
              required
              aria-invalid={!!error && !name.trim()}
              aria-describedby={error ? "kb-form-error" : undefined}
            />
          </div>
          <div className="grid gap-2">
            <label htmlFor="kb-description" className="text-sm font-medium">
              描述 <span className="font-normal text-muted-foreground">（可选）</span>
            </label>
            <Textarea
              id="kb-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="简单介绍知识库的用途和资料范围"
              rows={4}
              disabled={saving}
            />
          </div>
          {error && (
            <p id="kb-form-error" role="alert" className="text-xs text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" disabled={saving} onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              {saving ? "正在保存…" : base ? "保存修改" : "创建知识库"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
