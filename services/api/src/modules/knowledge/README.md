# 知识库模块

## 已完成

- [x] 知识库新增、分页查询、修改、删除，已对接前端。
- [x] 在线文档新建、编辑、自动保存、列表、读取与删除，使用PostgreSQL。
- [x] 保存标题、Markdown 正文、BlockNote 富文本块及创建/更新时间。
- [x] 旧 localStorage 在线文档首次读取时迁移；成功后清理旧副本。
- [x] 页面仅展示服务端知识库和文档；已移除示例库、本地上传回退及演示缓存 CRUD。旧在线文档迁移独立保留，接口失败展示错误并支持重试。

- [x] 上传 TXT / Markdown / PDF / Word（最大 20 MB），源文件保存到 `.dp-work/data/knowledge/<用户ID>/<知识库ID>/`，记录写入 PostgreSQL。
- [x] 上传文件列表、鉴权读取、PDF 预览及删除源文件；失败上传不保留记录和临时文件。

- [x] PDF 使用 Sidecar 的 `PyMuPDFLoader` 按页提取正文及 Markdown 表格，保存解析结果和页码到 PostgreSQL。
- [x] PDF 无文字层扫描页接入百度高精度 OCR，保留页码，失败不保存不完整结果；配置在 Sidecar `.env`，沿用解析任务通知。
- [x] 解析任务异步执行，支持失败重试、服务重启恢复；前端展示解析进度及源文档 / 解析后文档。
- [x] 解析完成或失败通过 WebSocket 推送，跨页面 Toast 通知，不再定时查询文档。
- [x] 解析结果支持富文本编辑、自动保存和并发修改冲突检查；源文件保持不变。
- [x] 列表主标签：未解析、已解析、已向量化。
- [x] TXT、Markdown 使用 LangChain TextLoader 解析，支持上传文件及在线文档；DOCX 使用 python-docx 保留标题、段落、列表、表格及基础样式；旧版 DOC、独立图片文件暂不处理。

- [x] 父子分块：按 Markdown 标题分组，父块约 2000 字符、重叠 200；子块约 500 字符、重叠 80。
- [x] 方舟 `doubao-embedding-vision-251215` 文本向量化，1024 维；子块向量保存在 pgvector，父块保存完整上下文和标题/可确认页码。
- [x] 向量化由 PostgreSQL 保存任务、租约和进度；重启恢复、失败重试、完成/失败 WebSocket 通知；全部子块成功后才发布索引。
- [x] 编辑正文立即使旧索引失效；删除文档级联删除父子块；过期任务不可写回。
- [x] `POST /api/knowledge-bases/search` 可独立检索；先限定用户/知识库，pgvector 语义检索与 Elasticsearch BM25 并行召回子块，RRF 融合后按父块去重。
- [x] Agent 关联知识库后提供 `search_knowledge` Tool，返回父块与文档引用；服务端签发 240 秒固定范围授权，不传用户 JWT。

- [x] Elasticsearch 中文关键词检索，支持型号空格/连字符归一化；任一路服务故障时降级到另一路。
- [x] ES 同步请求与文档变更同事务写入 PostgreSQL，后台租约执行、失败退避重试；已有向量自动回填，索引重建后自动恢复。
- [x] 编辑/删除立即通过 PG 权限与版本过滤，ES 异步清理；返回前再次校验当前文档版本。

## 混合检索运行

1. `docker-compose up -d postgres elasticsearch` 启动本地开发依赖。
2. 在 `services/api` 执行 `.venv/bin/python -m alembic upgrade head`。
3. 运行根目录 `pnpm mq:up` 和 `pnpm dev:workers`；解析、向量化、ES 同步由独立 Celery Worker 消费。
4. 配置 API 的 `ELASTICSEARCH_*`、`RAG_HYBRID_CANDIDATES`（每路候选默认 50）与 `RAG_RRF_CONSTANT`（默认 60），再启动 API / Sidecar。配置说明见 API `.env.example`。

Elasticsearch 保存可重建的文本子块索引，pgvector 保存向量，PG 保存正文、父块和权限。现有文档无需重新向量化；后台每 30 秒检查回填并投递 MQ，索引完成后即可混合检索。关闭 `ELASTICSEARCH_ENABLED` 可使用纯向量检索。ES 故障时检索自动降级，待服务恢复重试；查询向量故障时可使用已同步的关键词索引。Agent 的 `search_knowledge` 和独立检索接口共用该链路。

Compose 为本地开发配置，仅绑定回环地址且未开启 ES 鉴权；服务器部署配置 HTTPS、CA 和 ES API Key / Basic 认证，凭证仅存 API 环境变量。Sidecar 和浏览器不直接访问 ES。

测试：设置独立 `TEST_DATABASE_URL` 运行 API 测试；额外指定 `TEST_ELASTICSEARCH_URL` 可运行真实 ES 测试，使用随机临时索引，不操作应用索引。

任务配置与运行方式见 [异步任务说明](../../infrastructure/tasks/README.md)。

## 待完成

- [ ] 图文混排页面的插图 OCR、扫描表格结构还原、重排模型。

删除知识库会在同一事务删除其在线文档。
