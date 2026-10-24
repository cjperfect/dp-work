"use client";

import { useState } from "react";
import { CheckCircle2, Download, Package, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { AGENT_OPTIONS, SKILLS, type AgentTarget } from "@/features/skills/constants/skills";

/** 判断技能是否已安装给当前目标 Agent */
function matchesTarget(installedFor: AgentTarget[], target: AgentTarget): boolean {
  return installedFor.includes(target);
}

const targetLabel = (t: AgentTarget) => AGENT_OPTIONS.find((o) => o.value === t)?.label ?? t;

export function SkillsPage() {
  const [tab, setTab] = useState<"installed" | "available">("installed");
  const [target, setTarget] = useState<AgentTarget>("general");
  // 本地技能状态：卸载/安装先在前端流转（后端待接入）
  const [skills, setSkills] = useState(SKILLS);
  const [uninstallTarget, setUninstallTarget] = useState<string | null>(null);

  const installed = skills.filter(
    (s) => s.status === "installed" && matchesTarget(s.installedFor, target),
  );
  const available = skills.filter((s) => s.status === "available");
  const visible = tab === "installed" ? installed : available;

  const handleUninstall = () => {
    if (!uninstallTarget) return;
    setSkills((prev) =>
      prev.map((s) => {
        if (s.id !== uninstallTarget) return s;
        const next = s.installedFor.filter((t) => t !== target);
        return {
          ...s,
          installedFor: next,
          status: next.length === 0 ? ("available" as const) : ("installed" as const),
        };
      }),
    );
    setUninstallTarget(null);
  };

  const handleInstall = (id: string) => {
    setSkills((prev) =>
      prev.map((s) => {
        if (s.id !== id) return s;
        const next = [...new Set([...s.installedFor, target])] as ("general" | "product")[];
        return { ...s, installedFor: next, status: "installed" as const };
      }),
    );
  };

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">技能安装</h1>
        <p className="text-muted-foreground text-sm">
          每个部门一个 Agent，技能由部门业务范畴与 SOP 自动整理生成，安装后输出内容自动符合部门规范
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 border-b">
          <button
            type="button"
            onClick={() => setTab("installed")}
            className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
              tab === "installed"
                ? "border-primary text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <CheckCircle2 className="size-4" />
            已安装
            <span className="text-muted-foreground/60 text-xs">{installed.length}</span>
          </button>
          <button
            type="button"
            onClick={() => setTab("available")}
            className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
              tab === "available"
                ? "border-primary text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Package className="size-4" />
            未安装
            <span className="text-muted-foreground/60 text-xs">{available.length}</span>
          </button>
        </div>

        <Select value={target} onValueChange={(v) => setTarget(v as AgentTarget)}>
          <SelectTrigger className="min-w-36" aria-label="选择目标 Agent">
            <SelectValue placeholder="选择目标 Agent">
              {(v: string | null) => targetLabel(v as AgentTarget)}
            </SelectValue>
          </SelectTrigger>
          <SelectContent align="end">
            {AGENT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {tab === "installed" && (
        <p className="text-muted-foreground -mt-3 text-xs">当前展示：{targetLabel(target)}</p>
      )}

      <ul className="flex flex-col gap-3">
        {visible.map((skill) => (
          <li
            key={skill.id}
            className="flex items-start justify-between gap-4 rounded-xl border bg-card px-4 py-3.5"
          >
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{skill.name}</span>
                <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
                  {skill.department}
                </span>
              </div>
              <p className="text-muted-foreground text-sm">{skill.description}</p>
              {tab === "installed" && skill.installedFor.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-muted-foreground text-xs">已安装给</span>
                  {skill.installedFor.map((t) => (
                    <span
                      key={t}
                      className="bg-emerald-500/10 text-emerald-700 rounded px-1.5 py-0.5 text-xs font-medium"
                    >
                      {targetLabel(t)}
                    </span>
                  ))}
                </div>
              )}
            </div>
            {skill.status === "installed" ? (
              <div className="flex shrink-0 items-center gap-2">
                <span className="bg-emerald-500/10 text-emerald-600 flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
                  <CheckCircle2 className="size-3" />
                  已安装
                </span>
                <Popover
                  open={uninstallTarget === skill.id}
                  onOpenChange={(open) => setUninstallTarget(open ? skill.id : null)}
                >
                  <PopoverTrigger
                    render={
                      <Button variant="outline" size="sm">
                        卸载
                      </Button>
                    }
                  />
                  <PopoverContent align="end" className="w-64 p-3">
                    <p className="text-sm font-medium">卸载技能</p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      将「{skill.name}」从{targetLabel(target)}卸载，确定卸载吗？
                    </p>
                    <div className="mt-3 flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setUninstallTarget(null)}>
                        取消
                      </Button>
                      <Button variant="destructive" size="sm" onClick={handleUninstall}>
                        卸载
                      </Button>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            ) : (
              <div className="flex shrink-0 items-center gap-2">
                <span className="bg-muted text-muted-foreground flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
                  <XCircle className="size-3" />
                  未安装
                </span>
                <Button size="sm" onClick={() => handleInstall(skill.id)}>
                  <Download className="size-3.5" />
                  安装到{targetLabel(target)}
                </Button>
              </div>
            )}
          </li>
        ))}
        {visible.length === 0 && (
          <li className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
            {tab === "installed" ? `暂无已安装到${targetLabel(target)}的技能` : "暂无可安装技能"}
          </li>
        )}
      </ul>

      <p className="text-muted-foreground text-xs">* 技能列表与安装 / 卸载为 UI 骨架，功能待接入</p>
    </div>
  );
}
