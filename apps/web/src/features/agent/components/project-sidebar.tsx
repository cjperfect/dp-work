import { agentPath } from "@/features/agent/constants/agents";
import { useMemo, useState } from "react";
import { ThreadListPrimitive, useAui, useAuiState } from "@assistant-ui/react";
import { useNavigate } from "@tanstack/react-router";
import { ChevronDown, ChevronRight, Folder, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { ThreadListItem, ThreadListRoot } from "@/components/assistant-ui/elements/thread-list.aui";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SidebarGroup, SidebarGroupContent, SidebarGroupLabel } from "@/components/ui/sidebar";
import { deleteProject, loadProjects } from "@/stores/agent-projects";
import { createThread, selectThreadById, useAgentStore } from "@/stores/agent";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { useProjects } from "../hooks/use-projects";
import { useAgentCode } from "../hooks/use-agent-code";
import type { AgentProject } from "@/apis/agent-projects";
import type { ChatThread } from "@/types/agent";
import { CreateProjectDialog } from "./create-project-dialog";

export function ProjectSidebar() {
  const aui = useAui(),
    navigate = useNavigate(),
    code = useAgentCode();
  const owner = useAuthStore((s) => s.user?.id);
  const lists = useAgentStore((s) => s.lists);
  const { items, loading, error: loadError } = useProjects();
  const [createOpen, setCreateOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const groups = useMemo(() => {
    const result = new Map<string, ChatThread[]>();
    Object.values(lists)
      .flatMap((rows) => rows ?? [])
      .forEach((thread) => {
        if (thread.project_id && thread.has_history)
          result.set(thread.project_id, [...(result.get(thread.project_id) ?? []), thread]);
      });
    result.forEach((rows) => rows.sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    return result;
  }, [lists]);
  async function openThread(id: string) {
    const target = await selectThreadById(id);
    useAppStore.getState().setAgentId(target);
    await aui.threads.switchToThread(id);
    await navigate({ to: agentPath(target) });
  }
  async function newChat(projectId: string) {
    const id = await createThread(code, projectId);
    await aui.threads.reload();
    await openThread(id);
  }
  return (
    <SidebarGroup className="py-1">
      <div className="group/project-heading flex items-center justify-between pr-1">
        <SidebarGroupLabel className="h-8">
          <button
            className="flex items-center gap-1 hover:text-foreground"
            onClick={() => setCollapsed((value) => !value)}
            aria-expanded={!collapsed}
          >
            项目
            <ChevronDown
              className={`size-3 transition-transform ${collapsed ? "-rotate-90" : ""}`}
            />
          </button>
        </SidebarGroupLabel>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="添加项目文件夹"
          className="pointer-events-none opacity-0 transition-opacity group-hover/project-heading:pointer-events-auto group-hover/project-heading:opacity-100 group-focus-within/project-heading:pointer-events-auto group-focus-within/project-heading:opacity-100"
          title={
            window.desktop?.selectProjectDirectory ? "添加项目文件夹" : "请在桌面端添加本地文件夹"
          }
          disabled={!owner}
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="size-3.5" />
        </Button>
      </div>
      {!collapsed && (
        <SidebarGroupContent>
          {items.map((project) => (
            <ProjectRow
              key={project.id}
              project={project}
              threads={groups.get(project.id) ?? []}
              onNew={() => newChat(project.id)}
            />
          ))}
          {!items.length && !loading && (
            <p className="px-2 py-2 text-xs leading-5 text-muted-foreground">
              添加本地文件夹，将会话整理到项目中。
            </p>
          )}
          {loading && !items.length && (
            <p className="px-2 py-2 text-xs text-muted-foreground">正在读取项目…</p>
          )}
        </SidebarGroupContent>
      )}
      <CreateProjectDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={async (project) => {
          setCollapsed(false);
          await newChat(project.id);
        }}
      />
      {loadError && (
        <button
          className="px-2 text-left text-xs text-destructive"
          onClick={() => {
            void loadProjects(true);
          }}
        >
          {loadError}，点击重试
        </button>
      )}
    </SidebarGroup>
  );
}

function ProjectRow({
  project,
  threads,
  onNew,
}: {
  project: AgentProject;
  threads: ChatThread[];
  onNew(): Promise<void>;
}) {
  const [expanded, setExpanded] = useState(true),
    [showAll, setShowAll] = useState(false);
  const [menu, setMenu] = useState(false),
    [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  async function act(operation: () => Promise<unknown>, close = false) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await operation();
      if (close) setMenu(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目操作失败。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mb-1">
      <div className="group/project-row flex items-center gap-0.5 rounded-md hover:bg-sidebar-accent">
        <button
          className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left text-sm"
          title={project.path}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <Folder className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{project.name}</span>
          {!expanded && <ChevronRight className="size-3 shrink-0 text-muted-foreground" />}
        </button>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={`在${project.name}中新建会话`}
          className="pointer-events-none opacity-0 transition-opacity group-hover/project-row:pointer-events-auto group-hover/project-row:opacity-100 group-focus-within/project-row:pointer-events-auto group-focus-within/project-row:opacity-100"
          disabled={busy}
          onClick={() => void act(onNew)}
        >
          <Plus className="size-3.5" />
        </Button>
        <Popover
          open={menu}
          onOpenChange={(open) => {
            if (!busy) {
              setMenu(open);
              setConfirm(false);
            }
          }}
        >
          <PopoverTrigger
            render={
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`${project.name}项目操作`}
                className={`transition-opacity group-hover/project-row:pointer-events-auto group-hover/project-row:opacity-100 group-focus-within/project-row:pointer-events-auto group-focus-within/project-row:opacity-100 ${menu ? "opacity-100" : "pointer-events-none opacity-0"}`}
              />
            }
          >
            <MoreHorizontal className="size-3.5" />
          </PopoverTrigger>
          <PopoverContent side="right" align="start" className={confirm ? "w-72" : "w-40 p-1"}>
            {confirm ? (
              <>
                <h3 className="text-sm font-medium">移除项目？</h3>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  仅移除项目关联，本地文件和历史会话都会保留。
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => setConfirm(false)}
                  >
                    取消
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy}
                    onClick={() => void act(() => deleteProject(project.id), true)}
                  >
                    确认移除
                  </Button>
                </div>
              </>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                className="w-full justify-start text-destructive hover:text-destructive"
                disabled={busy}
                onClick={() => setConfirm(true)}
              >
                <Trash2 className="size-3.5" />
                移除项目
              </Button>
            )}
            {error && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                {error}
              </p>
            )}
          </PopoverContent>
        </Popover>
      </div>
      {expanded && (
        <div className="ml-5 grid border-l pl-1">
          <ProjectThreadList threads={showAll ? threads : threads.slice(0, 5)} />
          {!threads.length && (
            <button
              className="py-1.5 pl-3 text-left text-xs text-muted-foreground hover:text-foreground"
              disabled={busy}
              onClick={() => void act(onNew)}
            >
              新建会话
            </button>
          )}
          {threads.length > 5 && (
            <button
              className="py-1.5 pl-3 text-left text-xs text-muted-foreground"
              onClick={() => setShowAll((value) => !value)}
            >
              {showAll ? "收起" : `查看全部 ${threads.length} 个会话`}
            </button>
          )}
          {error && !menu && <p className="px-2 text-xs text-destructive">{error}</p>}
        </div>
      )}
    </div>
  );
}

/** 与最近会话复用同一行组件，统一重命名、删除确认与运行状态。 */
function ProjectThreadList({ threads }: { threads: ChatThread[] }) {
  const ids = useAuiState((s) => s.threads.threadIds);
  const items = useAuiState((s) => s.threads.threadItems);
  const indices = new Map(items.map((item) => [item.remoteId, ids.indexOf(item.id)]));
  return (
    <ThreadListRoot>
      {threads.map((thread) => {
        const index = indices.get(thread.id);
        return index !== undefined && index >= 0 ? (
          <ThreadListPrimitive.ItemByIndex
            key={thread.id}
            index={index}
            components={{ ThreadListItem }}
          />
        ) : null;
      })}
    </ThreadListRoot>
  );
}
