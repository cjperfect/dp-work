# 知识库模块

## 已完成

- [x] 知识库新增、分页查询、修改、删除，已对接前端。
- [x] 在线文档新建、编辑、自动保存、列表、读取与删除，使用PostgreSQL。
- [x] 保存标题、Markdown 正文、BlockNote 富文本块及创建/更新时间。
- [x] 旧 localStorage 在线文档首次读取时迁移；成功后清理旧副本。

- [x] 上传 TXT / Markdown / PDF / Word（最大 20 MB），源文件保存到 `.dp-work/data/knowledge/<用户ID>/<知识库ID>/`，记录写入 PostgreSQL。
- [x] 上传文件列表、鉴权读取、PDF 预览及删除源文件；失败上传不保留记录和临时文件。

- [x] PDF 使用 Sidecar 的 `PyMuPDFLoader` 按页提取正文及 Markdown 表格，保存解析结果和页码到 PostgreSQL。
- [x] 解析任务异步执行，支持失败重试、服务重启恢复；前端展示解析进度及源文档 / 解析后文档。
- [x] 解析完成或失败通过 WebSocket 推送，跨页面 Toast 通知，不再定时查询文档。
- [x] 解析结果支持富文本编辑、自动保存和并发修改冲突检查；源文件保持不变。
- [x] 列表主标签：未解析、已解析、已向量化。
- [x] TXT、Markdown 使用 LangChain TextLoader 解析，支持上传文件及在线文档；DOCX 使用 python-docx 保留标题、段落、列表、表格及基础样式；旧版 DOC、图片及 OCR 暂不处理。

- [x] 父子分块：按 Markdown 标题分组，父块约 2000 字符、重叠 200；子块约 500 字符、重叠 80。
- [x] 方舟 `doubao-embedding-vision-251215` 文本向量化，1024 维；子块向量保存在 pgvector，父块保存完整上下文和标题/可确认页码。
- [x] 向量化由 PostgreSQL 保存任务、租约和进度；重启恢复、失败重试、完成/失败 WebSocket 通知；全部子块成功后才发布索引。
- [x] 编辑正文立即使旧索引失效；删除文档级联删除父子块；过期任务不可写回。
- [x] `POST /api/knowledge-bases/search` 可独立检索；先限定用户/知识库，再对子块做余弦相似度检索，按父块最佳分数去重。
- [x] Agent 关联知识库后提供 `search_knowledge` Tool，返回父块与文档引用；服务端签发 240 秒固定范围授权，不传用户 JWT。

## 待完成

- [ ] OCR、重排模型及混合检索。

删除知识库会在同一事务删除其在线文档。
