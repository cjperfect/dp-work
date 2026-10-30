# Web

- 本应用使用 Vite、React、TanStack Router，不使用 Next.js。
- 源码放在 `src/`，路由入口放在 `src/routes/`。
- 业务组件和 Hook 放在对应的 `src/features/<module>/` 内。
- Store 统一放在 `src/stores/`，API 请求统一放在 `src/apis/`，按业务模块命名，例如 `knowledge.ts`、`meetings.ts`。
- 业务模型、接口请求与响应类型统一放在 `src/interfaces/`，按模块命名；API 和常量文件不再声明或重导出业务类型。通用 Axios HTTP 客户端保留在 `src/lib/http.ts`，所有请求实现放在 `src/apis/`，页面、Hook、Store 只调用 API 函数。API 层使用 `http.get/post/put/patch/delete`，写入请求按 `(path, data, options)` 传参，不再手写 method。
- 共享业务常量放在 `src/constants/`，按模块命名；不再在 feature 下新建 constants 目录。
- 通用组件放在 `src/components/`，通用 Hook 放在 `src/hooks/`。
- Hook 和 Store 文件名采用横杠命名（kebab-case），例如 `use-knowledge-bases.ts`、`knowledge-upload.ts`。
- `src/routeTree.gen.ts` 由 TanStack Router 自动生成，不手动修改。
- 新增 UI 优先复用现有 shadcn 组件。
- 不把服务端密钥放入前端环境变量。
