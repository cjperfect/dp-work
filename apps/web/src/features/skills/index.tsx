import type { CatalogSkill, InstalledSkill } from "@/interfaces/skills";
import type { AgentId } from "@/interfaces/app";
import { useRef, useState } from "react";
import { ExternalLink, Package, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAgentStore } from "@/stores/agent";
import { useAppStore } from "@/stores/app";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
import { useSkills } from "./hooks/use-skills";
import { SkillCard } from "./components/skill-card";
import { SkillDetailDialog } from "./components/skill-detail-dialog";

import { useSkillMarket } from "./hooks/use-skill-market";
import { useSkillActions } from "./hooks/use-skill-actions";

export function SkillsPage() {
  const uploadInput = useRef<HTMLInputElement>(null);
  const initial = useAgentCode();
  const [code, setCode] = useState<AgentId>(initial);
  const allAgents = useAgentStore((state) => state.agents);
  const partnerCodes = useAgentStore((state) => state.partnerCodes);
  const agents = allAgents.filter(
    (row) => row.code === "general" || partnerCodes.includes(row.code),
  );
  const agent = agents.find((row) => row.code === code);
  const setAgentId = useAppStore((state) => state.setAgentId);
  const { skills, loading, error, reload } = useSkills(code);
  const [tab, setTab] = useState("installed");
  const [detail, setDetail] = useState<InstalledSkill | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const { query, setQuery, updateSearch, descriptions, catalog, searching, searchError } =
    useSkillMarket(tab === "market");
  const { busy, operationError, clearError, upload, install, uninstall } = useSkillActions(
    code,
    agent?.name,
    () => setTab("installed"),
    () => setConfirm(null),
  );
  const installedIds = new Set(skills.map((skill) => skill.id));
  function card(skill: CatalogSkill | InstalledSkill, installed: boolean) {
    const description =
      skills.find((item) => item.id === skill.id)?.description ||
      skill.description ||
      descriptions[skill.id];
    return (
      <SkillCard
        key={skill.id}
        skill={skill}
        description={description}
        agentName={agent?.name ?? code}
        installed={installed}
        busy={busy}
        loading={loading}
        canInstall={!!agent}
        confirmOpen={confirm === skill.id}
        onView={() => setDetail(skill)}
        onInstall={() => void install(skill.id)}
        onUninstall={() => void uninstall(skill)}
        onConfirmChange={(open) => setConfirm(open ? skill.id : null)}
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8 md:px-10">
      <header className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <p className="mb-2 text-xs tracking-[.18em] text-muted-foreground">AGENT CAPABILITIES</p>
          <h1 className="text-2xl font-semibold">技能配置</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            从 skills.sh 安装业务技能，当前 Agent 会在对话中按需加载。点击技能名称查看详情。
          </p>
        </div>
        <a
          href="https://skills.sh"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          浏览 skills.sh
          <ExternalLink className="size-3.5" />
        </a>
      </header>
      <div className="mt-7 flex flex-wrap items-center gap-3 text-sm">
        <input
          ref={uploadInput}
          type="file"
          accept=".md,.zip"
          className="hidden"
          aria-label="上传技能文件"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void upload(file);
          }}
        />
        <Button
          variant="outline"
          disabled={!!busy || !agent}
          onClick={() => uploadInput.current?.click()}
        >
          上传技能
        </Button>
        <span className="text-xs text-muted-foreground">支持 SKILL.md / ZIP，最大 8 MB</span>
        <span>配置目标</span>
        <Select
          value={code}
          disabled={busy !== null}
          onValueChange={(value) => {
            if (value) {
              setCode(value as AgentId);
              setAgentId(value as AgentId);
              clearError();
              setConfirm(null);
            }
          }}
        >
          <SelectTrigger className="w-52" aria-label="技能配置目标">
            <SelectValue>
              {(value) => agents.find((row) => row.code === value)?.name ?? value}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {agents.map((row) => (
              <SelectItem key={row.code} value={row.code}>
                {row.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={loading || busy !== null}
          onClick={() => void reload()}
          aria-label="刷新已安装技能"
        >
          <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
        </Button>
      </div>
      {(error || operationError) && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {operationError ?? error}
        </p>
      )}
      <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="mt-6">
        <TabsList>
          <TabsTrigger value="installed">
            已安装
            <span className="ml-1 rounded-full bg-background px-1.5 text-xs tabular-nums">
              {skills.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="market">技能市场</TabsTrigger>
        </TabsList>
        <TabsContent value="installed" className="mt-5">
          {loading ? (
            <p role="status" className="py-10 text-center text-sm text-muted-foreground">
              正在读取当前设备的技能…
            </p>
          ) : skills.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {skills.map((skill) => card(skill, true))}
            </div>
          ) : (
            !error && (
              <div className="rounded-xl border border-dashed px-6 py-14 text-center">
                <Package className="mx-auto size-7 text-muted-foreground" />
                <h2 className="mt-4 text-sm font-medium">还没有安装技能</h2>
                <p className="mt-2 text-xs text-muted-foreground">
                  进入技能市场，为{agent?.name ?? "当前 Agent"}添加第一个技能。
                </p>
                <Button className="mt-5" size="sm" onClick={() => setTab("market")}>
                  浏览技能市场
                </Button>
              </div>
            )
          )}
        </TabsContent>
        <TabsContent value="market" className="mt-5">
          <div className="mb-5 rounded-xl border bg-muted/20 p-4">
            <label className="grid max-w-xl gap-2 text-xs text-muted-foreground">
              搜索技能
              <div className="relative">
                <Search className="absolute left-3 top-3 size-3.5" />
                <Input
                  className="bg-background pl-9"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    updateSearch(event.target.value);
                  }}
                  placeholder="搜索文档、产品分析、react…"
                />
              </div>
            </label>
          </div>
          {searchError && (
            <p role="alert" className="mb-4 text-sm text-destructive">
              {searchError}
            </p>
          )}
          {searching ? (
            <p role="status" className="py-10 text-center text-sm text-muted-foreground">
              正在搜索 skills.sh…
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {catalog.map((skill) => card(skill, installedIds.has(skill.id)))}
            </div>
          )}
          {!searching && !searchError && !catalog.length && (
            <p className="py-10 text-center text-sm text-muted-foreground">
              没有找到相关技能，请尝试其他关键词。
            </p>
          )}
        </TabsContent>
      </Tabs>
      <SkillDetailDialog
        key={`${code}:${detail?.id ?? "closed"}`}
        skill={
          detail
            ? {
                ...detail,
                description:
                  skills.find((item) => item.id === detail.id)?.description ||
                  detail.description ||
                  descriptions[detail.id] ||
                  "",
              }
            : null
        }
        agentName={agent?.name ?? code}
        installed={detail !== null && installedIds.has(detail.id)}
        busy={busy !== null}
        onClose={() => setDetail(null)}
        onInstall={() => {
          if (detail) void install(detail.id);
        }}
      />
      <p className="mt-6 text-xs leading-6 text-muted-foreground">
        技能保存在本机当前 Agent 的 workspace/skills
        目录，刷新后仍可读取。安装完成后，下次对话会自动加载。
      </p>
    </div>
  );
}
