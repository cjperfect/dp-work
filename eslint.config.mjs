import { defineConfig, globalIgnores } from "eslint/config";
import js from "@eslint/js";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import eslintConfigPrettier from "eslint-config-prettier/flat";

export default defineConfig([
  globalIgnores([
    "**/node_modules/**",
    "**/.next/**",
    "**/out/**",
    "**/build/**",
    "**/dist/**",
    "**/coverage/**",
  ]),
  js.configs.recommended,
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // App Router 项目没有 pages 目录，eslint-config-next 的该规则误报
      "@next/next/no-html-link-for-pages": "off",
      // 允许 catch {} 吞异常（模板与工具代码的常见写法）
      "no-empty": ["error", { allowEmptyCatch: true }],
      // eslint-plugin-react-hooks 6.x 新增规则，与 useRef 缓存值、
      // effect 内同步 setState 的常见 React 模式冲突，关闭避免误报
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
  eslintConfigPrettier,
]);
