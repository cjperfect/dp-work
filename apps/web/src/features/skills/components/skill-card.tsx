import { ExternalLink, Loader2, Package, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { CatalogSkill, InstalledSkill } from "@/apis/skills";

type Props = {
  skill: CatalogSkill | InstalledSkill;
  description?: string;
  agentName: string;
  installed: boolean;
  busy: string | null;
  loading: boolean;
  canInstall: boolean;
  confirmOpen: boolean;
  onView(): void;
  onInstall(): void;
  onUninstall(): void;
  onConfirmChange(open: boolean): void;
};

export function SkillCard({
  skill,
  description,
  agentName,
  installed,
  busy,
  loading,
  canInstall,
  confirmOpen,
  onView,
  onInstall,
  onUninstall,
  onConfirmChange,
}: Props) {
  const brief = description?.replace(/\s+/g, " ").trim();
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-xl border bg-card p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted">
          <Package className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="break-words text-sm font-semibold">
            <button
              type="button"
              className="text-left hover:underline"
              onClick={() => onView()}
              aria-label={`查看技能 ${skill.name} 详情`}
            >
              {skill.name}
            </button>
          </h2>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {skill.source || "本机技能"}
          </p>
        </div>
        {skill.url && (
          <a
            href={skill.url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-muted-foreground hover:text-foreground"
            aria-label={`在 skills.sh 查看 ${skill.name}`}
          >
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
      <button
        type="button"
        onClick={() => onView()}
        className="min-h-18 text-left text-xs leading-6 text-muted-foreground hover:text-foreground"
        aria-label={`阅读 ${skill.name} 技能说明`}
      >
        <span className="line-clamp-3">
          {brief || (description === undefined ? "正在读取技能简介…" : "暂未提供技能简介")}
        </span>
      </button>
      <div className="mt-auto flex items-center justify-between gap-3 border-t pt-4">
        <span className="text-[11px] text-muted-foreground">
          {installed
            ? `已安装到${agentName}`
            : "installs" in skill && skill.installs
              ? `${skill.installs.toLocaleString()} 次安装`
              : "来自 skills.sh"}
        </span>
        {installed ? (
          <Popover
            open={confirmOpen}
            onOpenChange={(open) => {
              if (!busy) onConfirmChange(open);
            }}
          >
            <PopoverTrigger
              render={
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={busy !== null}
                  aria-label={`卸载技能 ${skill.name}`}
                />
              }
            >
              <Trash2 className="size-3.5" />
              卸载
            </PopoverTrigger>
            <PopoverContent align="end">
              <h3 className="text-sm font-medium">卸载技能？</h3>
              <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
                从{agentName}移除「{skill.name}」，其他 Agent 的安装不受影响。
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => onConfirmChange(false)}
                >
                  取消
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busy !== null}
                  onClick={() => onUninstall()}
                >
                  {busy === skill.id && <Loader2 className="size-3.5 animate-spin" />}确认卸载
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        ) : (
          <Button
            size="sm"
            disabled={busy !== null || loading || !canInstall}
            onClick={() => onInstall()}
          >
            {busy === skill.id ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Plus className="size-3.5" />
            )}
            {busy === skill.id ? "安装中…" : `安装到${agentName}`}
          </Button>
        )}
      </div>
    </article>
  );
}
