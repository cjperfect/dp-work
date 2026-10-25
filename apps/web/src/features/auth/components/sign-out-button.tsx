import { useId, useState } from "react";
import { useRouter } from "@tanstack/react-router";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { signOut } from "@/stores/auth";

export function SignOutButton() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const titleId = useId();
  const descriptionId = useId();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="icon-sm" aria-label="退出登录">
            <LogOut className="size-4" />
          </Button>
        }
      />
      <PopoverContent
        align="end"
        className="w-64 p-3"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <h2 id={titleId} className="text-sm font-medium">
          确认退出登录？
        </h2>
        <p id={descriptionId} className="mt-1 text-xs text-muted-foreground">
          退出后需要重新登录才能继续使用工作空间。
        </p>
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={async () => {
              setOpen(false);
              signOut();
              await router.navigate({
                to: "/sign-in",
                search: { redirect: "/" },
                replace: true,
              });
            }}
          >
            确认退出
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
