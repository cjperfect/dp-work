"use client";

import { useRef, useState, type FormEvent } from "react";
import { Link, useRouter, useSearch } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpen,
  Check,
  Eye,
  EyeOff,
  Loader2,
  Sparkles,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authenticate, safeRedirect } from "@/features/auth/lib/auth";

function AuthPage({ mode }: { mode: "login" | "register" }) {
  const isRegister = mode === "register";
  const router = useRouter();
  const search = useSearch({ strict: false });
  const destination = safeRedirect(search.redirect);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;
    const data = new FormData(event.currentTarget);
    const username = String(data.get("username") ?? "").trim();
    const password = String(data.get("password") ?? "");
    if (!username || !password) {
      setError("请输入用户名和密码。");
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await authenticate(mode, username, password);
      await router.navigate({ href: destination, replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败，请重试。");
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-dvh bg-[#fbfaf8] text-[#242624] lg:grid-cols-[1fr_1fr]">
      <section className="flex min-h-dvh flex-col bg-white px-6 py-7 sm:px-12 lg:px-14 xl:px-20">
        <div className="flex items-center gap-2.5 text-sm font-semibold tracking-tight">
          <span className="flex size-8 items-center justify-center rounded-lg bg-[#252825] text-white">
            <Sparkles className="size-4" aria-hidden="true" />
          </span>
          企业 Agent 平台
        </div>

        <div className="mx-auto flex w-full max-w-[360px] flex-1 flex-col justify-center py-16">
          <div className="mb-8">
            <p className="mb-4 flex items-center gap-2 text-xs tracking-wide text-[#797d77]">
              <span className="size-1.5 rounded-full bg-[#6e8270]" />
              你的团队工作空间
            </p>
            <h1 className="text-[32px] font-semibold tracking-tight sm:text-4xl">
              {isRegister ? "创建你的账号" : "欢迎回来"}
            </h1>
            <p className="mt-3 text-sm leading-6 text-[#858780]">
              {isRegister
                ? "从这里开始，与团队一起把想法变成行动。"
                : "登录工作空间，继续与你的 Agent 协作。"}
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="space-y-5"
            aria-label={isRegister ? "注册" : "登录"}
          >
            <div className="space-y-2">
              <label htmlFor="username" className="text-[13px] font-medium">
                用户名
              </label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                placeholder={isRegister ? "设置你的用户名" : "请输入用户名"}
                required
                minLength={isRegister ? 2 : 1}
                maxLength={32}
                pattern={isRegister ? "\\S+" : undefined}
                title={isRegister ? "用户名为 2–32 个字符，不含空格" : undefined}
                disabled={submitting}
                aria-invalid={!!error}
                aria-describedby={error ? "auth-error" : undefined}
                className="h-11 rounded-lg border-[#e2e3df] bg-white px-3.5 text-sm shadow-none placeholder:text-[#b2b4ae]"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-[13px] font-medium">
                密码
              </label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  placeholder={isRegister ? "设置密码，至少 8 位" : "请输入密码"}
                  required
                  minLength={isRegister ? 8 : 1}
                  maxLength={128}
                  disabled={submitting}
                  aria-invalid={!!error}
                  aria-describedby={error ? "auth-error" : undefined}
                  className="h-11 rounded-lg border-[#e2e3df] bg-white pl-3.5 pr-11 text-sm shadow-none placeholder:text-[#b2b4ae]"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  disabled={submitting}
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  aria-pressed={showPassword}
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-lg text-[#969a92] hover:text-[#242624] focus-visible:outline-2 focus-visible:outline-offset-2"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {isRegister && (
                <p className="text-xs text-[#969a92]">用户名 2–32 个字符，密码至少 8 位。</p>
              )}
            </div>
            {error && (
              <p
                id="auth-error"
                role="alert"
                className="rounded-lg bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700"
              >
                {error}
              </p>
            )}
            <Button
              type="submit"
              disabled={submitting}
              className="mt-2 h-11 w-full rounded-lg bg-[#282c28] text-sm text-white hover:bg-[#3a4039]"
            >
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  {isRegister ? "正在创建…" : "正在登录…"}
                </>
              ) : (
                <>
                  {isRegister ? "创建账号" : "登录"}
                  <ArrowRight className="ml-1 size-4" />
                </>
              )}
            </Button>
          </form>
          <p className="mt-7 text-center text-[13px] text-[#969a92]">
            {isRegister ? "已有账号？" : "还没有账号？"}
            <Link
              to={isRegister ? "/sign-in" : "/sign-up"}
              search={{ redirect: destination }}
              className="ml-1.5 rounded-sm font-medium text-[#343c32] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-4"
            >
              {isRegister ? "去登录" : "创建账号"}
            </Link>
          </p>
        </div>
        <p className="text-[11px] tracking-wide text-[#aaada5]">
          部门 Agent · 会议纪要 · 企业知识库
        </p>
      </section>

      <aside className="relative hidden flex-col justify-center overflow-hidden border-l border-[#e8e8e0] px-12 py-14 lg:flex xl:px-20">
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-45 [background-image:radial-gradient(#c7cabe_0.7px,transparent_0.7px)] [background-size:22px_22px]"
        />
        <div className="relative mx-auto w-full max-w-[440px]">
          <span className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#929888]">
            A shared space. A smarter team.
          </span>
          <h2 className="mt-6 text-[34px] font-medium leading-[1.5] tracking-tight xl:text-[40px]">
            把团队的经验，
            <br />
            变成下一次行动。
          </h2>
          <p className="mt-5 max-w-[320px] text-sm leading-7 text-[#83897d]">
            让业务规范、会议中的共识与积累的知识，
            <br className="hidden xl:block" />
            在同一个工作空间里连接起来。
          </p>
          <div aria-hidden="true" className="relative mt-14 space-y-5">
            <div className="absolute left-[23px] top-7 bottom-7 w-px bg-[#d8ddcf]" />
            {[
              {
                icon: Workflow,
                label: "部门 Agent",
                detail: "遵循业务 SOP，让每一步有据可依",
                tag: "协作",
              },
              {
                icon: Check,
                label: "会议共识",
                detail: "从讨论中，整理决策与下一步行动",
                tag: "沉淀",
              },
              {
                icon: BookOpen,
                label: "团队知识",
                detail: "把一次的经验，变成团队的积累",
                tag: "复用",
              },
            ].map(({ icon: Icon, label, detail, tag }, index) => (
              <div
                key={label}
                className="relative flex items-center gap-4 rounded-xl border border-[#e2e5da] bg-[#fbfcf8] py-4 pl-3 pr-4 shadow-[0_3px_12px_#333d2610]"
                style={{ marginLeft: index === 1 ? 24 : 0 }}
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-[#e0e5d8] bg-[#f0f3e9] text-[#6a795d]">
                  <Icon className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium">{label}</p>
                  <p className="mt-1 text-[11px] text-[#92988b]">{detail}</p>
                </div>
                <span className="text-[10px] text-[#9ba28f]">{tag}</span>
              </div>
            ))}
          </div>
          <p className="mt-12 font-mono text-[10px] tracking-[0.15em] text-[#a2a895]">
            KNOWLEDGE → CONTEXT → ACTION
          </p>
        </div>
      </aside>
    </main>
  );
}

export function SignInPage() {
  return <AuthPage mode="login" />;
}
export function SignUpPage() {
  return <AuthPage mode="register" />;
}
