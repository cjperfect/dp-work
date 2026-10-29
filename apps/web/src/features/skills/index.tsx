import { useEffect, useMemo, useState } from "react";
import { debounce } from "es-toolkit/function";
import { ExternalLink, Package, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";
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
import { loadSkills } from "@/stores/skills";
import { getAccessToken } from "@/stores/auth";
import { useAppStore } from "@/stores/app";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
import { useSkills } from "./hooks/use-skills";
import { SkillCard } from "./components/skill-card";
import { SkillDetailDialog } from "./components/skill-detail-dialog";
import {
  searchSkills,
  getSkillDescriptions,
  installSkill,
  uninstallSkill,
  type CatalogSkill,
  type InstalledSkill,
} from "@/apis/skills";
import type { AgentId } from "@/interfaces/app";

export function SkillsPage() {
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
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [descriptions, setDescriptions] = useState<Record<string, string>>({});
  const [catalog, setCatalog] = useState<CatalogSkill[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [detail, setDetail] = useState<InstalledSkill | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const updateSearch = useMemo(() => debounce((value: string) => setSearch(value), 400), []);
  useEffect(() => () => updateSearch.cancel(), [updateSearch]);
  useEffect(() => {
    if (tab !== "market") return;
    const controller = new AbortController();
    setSearching(true);
    setSearchError(null);
    searchSkills(search, controller.signal)
      .then(({ items }) => {
        if (controller.signal.aborted) return;
        setCatalog(items);
        setSearching(false);
        const ids = items.filter((item) => !item.description).map((item) => item.id);
        if (ids.length)
          void getSkillDescriptions(ids, controller.signal)
            .then(({ items: summaries }) => {
              if (!controller.signal.aborted)
                setDescriptions((previous) => ({ ...previous, ...summaries }));
            })
            .catch(() => {
              if (!controller.signal.aborted)
                setDescriptions((previous) => ({
                  ...previous,
                  ...Object.fromEntries(ids.map((id) => [id, ""])),
                }));
            });
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setSearchError(cause instanceof Error ? cause.message : "技能搜索失败。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setSearching(false);
      });
    return () => controller.abort();
  }, [search, tab]);

  async function install(value: string) {
    if (busy || !agent) return;
    const token = getAccessToken();
    setBusy(value);
    setOperationError(null);
    try {
      await installSkill(code, value);
      if (token !== getAccessToken()) return;
      const refreshed = await loadSkills(code, true);
      if (token !== getAccessToken()) return;
      if (refreshed) toast.success(`已安装到${agent.name}，下次对话自动加载`);
      else toast.warning("技能已安装，但列表刷新失败，请点击刷新重试。");
    } catch (cause) {
      if (token === getAccessToken())
        setOperationError(cause instanceof Error ? cause.message : "安装失败，请重试。");
    } finally {
      setBusy(null);
    }
  }
  async function uninstall(skill: InstalledSkill) {
    if (busy) return;
    const token = getAccessToken();
    setBusy(skill.id);
    setOperationError(null);
    try {
      await uninstallSkill(code, skill.id);
      if (token !== getAccessToken()) return;
      const refreshed = await loadSkills(code, true);
      if (token !== getAccessToken()) return;
      setConfirm(null);
      if (refreshed) toast.success("技能已卸载");
      else toast.warning("技能已卸载，但列表刷新失败，请点击刷新重试。");
    } catch (cause) {
      if (token === getAccessToken())
        setOperationError(cause instanceof Error ? cause.message : "卸载失败，请重试。");
    } finally {
      setBusy(null);
    }
  }
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
        <span>配置目标</span>
        <Select
          value={code}
          disabled={busy !== null}
          onValueChange={(value) => {
            if (value) {
              setCode(value as AgentId);
              setAgentId(value as AgentId);
              setOperationError(null);
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
