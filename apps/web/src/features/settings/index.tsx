import type { PersonalSettings } from "@/interfaces/settings";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ChevronRight,
  ChartNoAxesColumn,
  Cpu,
  LoaderCircle,
  Mic,
  Monitor,
  Moon,
  Palette,
  Settings2,
  Sun,
  UserRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth";
import { usePreferences, updatePreferences, type Theme } from "@/stores/preferences";
import { getSettings } from "@/apis/settings";

import { Row, Group } from "./components/settings-fields";
import { ServiceForm } from "./components/service-form";
import { UsageSummary } from "./components/usage-summary";
const errorMessage = (cause: unknown) =>
  cause instanceof Error ? cause.message : "操作失败，请重试。";

const sections = [
  { id: "account", zh: "个人账号", icon: UserRound },
  { id: "appearance", zh: "外观", icon: Palette },
  { id: "model", zh: "模型服务", icon: Cpu },
  { id: "asr", zh: "会议转写", icon: Mic },
  { id: "usage", zh: "用量统计", icon: ChartNoAxesColumn },
] as const;
type SectionId = (typeof sections)[number]["id"];
export function SettingsPage() {
  const user = useAuthStore((state) => state.user);
  const theme = usePreferences((state) => state.theme);
  const [active, setActive] = useState<SectionId>("account");
  const [data, setData] = useState<PersonalSettings | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  const anchors = useRef<Partial<Record<SectionId, HTMLElement>>>({});
  useEffect(() => {
    let alive = true;
    setData(null);
    setLoadError("");
    if (user?.id)
      void (async () => {
        try {
          const value = await getSettings();
          if (alive) setData(value);
        } catch (cause) {
          if (alive) setLoadError(errorMessage(cause));
        }
      })();
    return () => {
      alive = false;
    };
  }, [user?.id, reload]);
  const goTo = (id: SectionId) => {
    const container = scroll.current,
      target = anchors.current[id];
    if (!container || !target) return;
    setActive(id);
    container.scrollTo({
      top:
        target.getBoundingClientRect().top -
        container.getBoundingClientRect().top +
        container.scrollTop -
        32,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  };
  const section = (id: SectionId, title: string, description: string, children: ReactNode) => (
    <section
      id={`settings-${id}`}
      ref={(node) => {
        if (node) anchors.current[id] = node;
      }}
      className="scroll-mt-8 space-y-4"
      aria-labelledby={`heading-${id}`}
    >
      <div>
        <h2 id={`heading-${id}`} className="text-base font-semibold tracking-tight">
          {title}
        </h2>
        <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">{description}</p>
      </div>
      {children}
    </section>
  );
  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <aside className="shrink-0 border-b bg-muted/15 px-4 py-5 md:w-52 md:border-r md:border-b-0 md:px-3 md:py-7 lg:w-60">
        <div className="mb-5 flex items-center gap-2 px-3">
          <Settings2 className="size-4" />
          <h1 className="text-lg font-semibold tracking-tight">{"设置"}</h1>
        </div>
        <p className="text-muted-foreground mb-2 hidden px-3 text-xs md:block">{"个人"}</p>
        <nav aria-label={"设置分类"} className="flex gap-1 overflow-x-auto md:flex-col">
          {sections.map(({ id, zh, icon: Icon }) => (
            <button
              type="button"
              key={id}
              onClick={() => goTo(id)}
              aria-current={active === id ? "location" : undefined}
              className={`flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring ${active === id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"}`}
            >
              <Icon className="size-4" />
              <span>{zh}</span>
              <ChevronRight
                className={`ml-auto hidden size-3 text-muted-foreground md:block ${active !== id ? "invisible" : ""}`}
              />
            </button>
          ))}
        </nav>
      </aside>
      <div
        ref={scroll}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
        onScroll={() => {
          const root = scroll.current;
          if (!root) return;
          if (root.scrollTop + root.clientHeight >= root.scrollHeight - 4) {
            setActive(sections[sections.length - 1].id);
            return;
          }
          const threshold = root.getBoundingClientRect().top + 90;
          let next: SectionId = "account";
          for (const item of sections)
            if ((anchors.current[item.id]?.getBoundingClientRect().top ?? Infinity) <= threshold)
              next = item.id;
          setActive(next);
        }}
      >
        <div className="mx-auto max-w-[880px] space-y-12 px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
          {section(
            "account",
            "个人账号",
            "你的工作空间账号信息。",
            <Group>
              <Row label={"用户名"}>
                <p className="text-right text-sm">{user?.username ?? "—"}</p>
              </Row>
              <Row label={"角色"}>
                <p className="text-right text-sm">
                  {user?.role === "admin"
                    ? "管理员"
                    : user?.role === "member"
                      ? "成员"
                      : (user?.role ?? "—")}
                </p>
              </Row>
              <Row label={"所属部门"}>
                <p className="text-right text-sm">{user?.department || "—"}</p>
              </Row>
            </Group>,
          )}
          {section(
            "appearance",
            "外观",
            "调整当前设备的显示偏好，修改后立即生效。",
            <Group>
              <Row label={"主题"} description={"跟随系统会自动适配设备的浅色和深色模式。"}>
                <div className="flex gap-1 rounded-lg bg-muted/60 p-1">
                  {[
                    { value: "light", label: "浅色", Icon: Sun },
                    { value: "dark", label: "深色", Icon: Moon },
                    { value: "system", label: "系统", Icon: Monitor },
                  ].map(({ value, label, Icon }) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={theme === value}
                      onClick={() => updatePreferences({ theme: value as Theme })}
                      className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs transition-colors focus-visible:ring-2 focus-visible:ring-ring ${theme === value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                    >
                      <Icon className="size-3.5" />
                      {label}
                    </button>
                  ))}
                </div>
              </Row>
            </Group>,
          )}
          {(["model", "asr"] as const).map((kind) => (
            <div key={kind}>
              {section(
                kind,
                kind === "model" ? "模型服务" : "会议转写",
                kind === "model"
                  ? "配置 Agent 对话与会议纪要使用的模型服务。"
                  : "配置会议实时转写使用的豆包 ASR 服务。",
                data ? (
                  <ServiceForm
                    key={`${user?.id}:${kind}`}
                    kind={kind}
                    initial={data[kind]}
                    onSaved={(value) =>
                      setData((current) => (current ? { ...current, [kind]: value } : current))
                    }
                  />
                ) : (
                  <div className="rounded-2xl border px-5 py-6 text-sm text-muted-foreground">
                    {loadError ? (
                      <div className="flex items-center justify-between gap-4">
                        <span role="alert">{loadError}</span>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setReload((value) => value + 1)}
                        >
                          {"重试"}
                        </Button>
                      </div>
                    ) : user ? (
                      <span className="flex items-center gap-2">
                        <LoaderCircle className="size-4 animate-spin" />
                        {"正在读取配置…"}
                      </span>
                    ) : (
                      "登录后可配置个人服务。"
                    )}
                  </div>
                ),
              )}
            </div>
          ))}
          {section(
            "usage",
            "用量统计",
            "按能力查看当前账号的本机累计用量与估算费用。",
            <UsageSummary />,
          )}
        </div>
      </div>
    </div>
  );
}
