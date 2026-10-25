import { useRef, useState } from "react";
import { Copy, Loader2, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { createMinutesShare, type Workspace } from "@/apis/meetings";
export function MinutesShare({
  workspace,
  beforeShare,
}: {
  workspace: Workspace;
  beforeShare: () => Promise<void>;
}) {
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const lock = useRef(false);
  async function create() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      await beforeShare();
      setLink(await createMinutesShare(workspace, "read"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建分享链接失败");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <Popover
      onOpenChange={(open) => {
        if (open) void create();
      }}
    >
      <PopoverTrigger
        render={
          <Button variant="outline">
            <Share2 className="size-4" />
            分享
          </Button>
        }
      />
      <PopoverContent
        align="end"
        className="w-80 max-w-[calc(100vw-2rem)]"
        aria-labelledby="minutes-share-title"
      >
        <h2 id="minutes-share-title" className="text-sm font-medium">
          分享会议纪要
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          本地演示链接仅在当前浏览器中有效。
        </p>
        {busy && !link && (
          <p role="status" className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            正在读取分享链接…
          </p>
        )}
        {link && (
          <div className="mt-3 flex gap-2">
            <Input
              readOnly
              aria-label="会议分享链接"
              value={link}
              onFocus={(event) => event.target.select()}
            />
            <Button
              variant="outline"
              size="icon"
              aria-label="复制分享链接"
              onClick={() => {
                void navigator.clipboard
                  .writeText(link)
                  .then(() => setCopied(true))
                  .catch(() => setError("复制失败，请手动复制链接。"));
              }}
            >
              <Copy className="size-4" />
            </Button>
          </div>
        )}
        {copied && (
          <p role="status" className="mt-2 text-xs text-emerald-700">
            链接已复制
          </p>
        )}
        {error && (
          <p role="alert" className="mt-3 text-xs text-destructive">
            {error}
            {!link && (
              <Button
                variant="ghost"
                size="xs"
                className="ml-2"
                disabled={busy}
                onClick={() => void create()}
              >
                重试
              </Button>
            )}
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
