import { useId, useState } from "react";
import { Link, useRouter } from "@tanstack/react-router";
import { LogOut, Settings, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { signOut, useAuthStore } from "@/stores/auth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export function UserMenu() {
  const user = useAuthStore((state) => state.user);
  const [confirm, setConfirm] = useState(false);
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const titleId = useId();
  const descriptionId = useId();

  if (!user) return null;
  return (
    <Popover
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        setConfirm(false);
      }}
    >
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            className="h-12 w-full justify-start gap-2 px-2"
            aria-label="用户菜单"
          >
            <Avatar>
              <AvatarFallback className="bg-sky-600 text-xs text-white">
                {user.username.slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <span className="min-w-0 flex-1 truncate text-left font-normal">{user.username}</span>
            <ChevronUp className="size-3.5 text-muted-foreground" />
          </Button>
        }
      />
      <PopoverContent
        side="top"
        align="start"
        className="w-64 rounded-2xl p-2"
        aria-labelledby={confirm ? titleId : undefined}
        aria-describedby={confirm ? descriptionId : undefined}
      >
        {confirm ? (
          <div className="p-1">
            <h2 id={titleId} className="text-sm font-medium">
              确认退出登录？
            </h2>
            <p id={descriptionId} className="mt-1 text-xs text-muted-foreground">
              退出后需要重新登录才能继续使用工作空间。
            </p>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>
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
          </div>
        ) : (
          <>
            <div className="mb-1 flex items-center gap-2 border-b px-2 py-3">
              <Avatar>
                <AvatarFallback className="bg-sky-600 text-xs text-white">
                  {user.username.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <span className="truncate text-sm font-medium">{user.username}</span>
            </div>
            <Button
              variant="ghost"
              className="w-full justify-start font-normal"
              nativeButton={false}
              render={<Link to="/settings" />}
              onClick={() => setOpen(false)}
            >
              <Settings className="size-4" />
              设置
            </Button>
            <Button
              variant="ghost"
              className="w-full justify-start font-normal"
              onClick={() => setConfirm(true)}
            >
              <LogOut className="size-4" />
              退出登录
            </Button>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}
