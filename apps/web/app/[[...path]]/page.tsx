"use client";

import { useEffect, useState } from "react";
import { AppRouter } from "@/router";

/**
 * 应用唯一入口：由 TanStack Router 接管全部视图路由（/、/product、/meetings、
 * /skills、/knowledge）。服务端渲染阶段返回空壳，水合后按当前 URL 渲染。
 */
export default function RootPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return <AppRouter />;
}
