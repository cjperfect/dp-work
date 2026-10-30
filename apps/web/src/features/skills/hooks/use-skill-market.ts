import type { CatalogSkill } from "@/interfaces/skills";
import { useEffect, useMemo, useState } from "react";
import { debounce } from "es-toolkit/function";
import { searchSkills, getSkillDescriptions } from "@/apis/skills";

/** 管理市场检索、防抖、简介补齐及离开页面后的请求取消。 */
export function useSkillMarket(active: boolean) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [descriptions, setDescriptions] = useState<Record<string, string>>({});
  const [catalog, setCatalog] = useState<CatalogSkill[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const updateSearch = useMemo(() => debounce((value: string) => setSearch(value), 400), []);
  useEffect(() => () => updateSearch.cancel(), [updateSearch]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setSearching(true);
    setSearchError(null);
    void (async () => {
      try {
        const { items } = await searchSkills(search, controller.signal);
        if (controller.signal.aborted) return;
        setCatalog(items);
        setSearching(false);
        const ids = items.filter((item) => !item.description).map((item) => item.id);
        if (ids.length) {
          try {
            const { items: summaries } = await getSkillDescriptions(ids, controller.signal);
            if (!controller.signal.aborted)
              setDescriptions((previous) => ({ ...previous, ...summaries }));
          } catch {
            if (!controller.signal.aborted)
              setDescriptions((previous) => ({
                ...previous,
                ...Object.fromEntries(ids.map((id) => [id, ""])),
              }));
          }
        }
      } catch (cause: unknown) {
        if (!controller.signal.aborted)
          setSearchError(cause instanceof Error ? cause.message : "技能搜索失败。");
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    })();
    return () => controller.abort();
  }, [search, active]);

  return { query, setQuery, updateSearch, descriptions, catalog, searching, searchError };
}
