# Web

- 本应用使用 Vite、React、TanStack Router，不使用 Next.js。
- 源码放在 `src/`，路由入口放在 `src/routes/`。
- 业务组件和 Hook 放在对应的 `src/features/<module>/` 内。
- Store 统一放在 `src/stores/`，API 请求统一放在 `src/apis/`，按业务模块命名，例如 `knowledge.ts`、`meetings.ts`。
- 纯业务类型放在 `src/types/`，通用 Axios HTTP 客户端保留在 `src/lib/http.ts`，业务接口复用统一请求函数。
- 通用组件放在 `src/components/`，通用 Hook 放在 `src/hooks/`。
- Hook 和 Store 文件名采用横杠命名（kebab-case），例如 `use-knowledge-bases.ts`、`knowledge-upload.ts`。
- `src/routeTree.gen.ts` 由 TanStack Router 自动生成，不手动修改。
- 新增 UI 优先复用现有 shadcn 组件。
- 不把服务端密钥放入前端环境变量。
