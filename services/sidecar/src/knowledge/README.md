# 知识库处理

- `parsers/pdf.py`：PyMuPDFLoader 提取 PDF 正文和 Markdown 表格，逐页保存页码，不启用 OCR 或图片识别。
- `parsers/word.py`：python-docx 按顺序提取 DOCX 标题、段落、列表和普通表格，生成 Markdown 与 BlockNote 块；旧版 DOC、图片及复杂排版暂不处理。
- `parsers/text.py`：TXT 与 Markdown 以 UTF-8 读取，统一换行并清理无效控制字符，Markdown 保留原有结构。
- `parsers/dispatcher.py`：独立子进程执行 PDF 解析，超时和取消时结束进程并清理临时文件；TXT、Markdown 使用 LangChain TextLoader 读取，DOCX 使用独立子进程执行。
- 内部接口 `POST /internal/knowledge/parse`：API 使用内部凭证发送文件字节和 `file_type`（pdf / txt / md / docx），在线文档发送已保存的正文，无需共享文件系统。
- 限制：文件最大 20 MB、提取正文最大 8 MB；PDF 最多 200 页，PDF 子进程超时由 `PDF_PARSE_TIMEOUT` 控制。
- 解析结果包含 `content`、来源 `metadata`（PDF 含页码）、`parser`，任务和结果由 API 存入 PostgreSQL。
- 解析结果支持前端人工修订，再进行父子分块：父块 2000 / 重叠 200，子块 500 / 重叠 80 字符。
- `rag/chunking.py` 保留标题层级；页码仅在正文仍可精确对应源页时保留。
- `rag/embedding.py` 使用 LangChain Embeddings 异步接口适配方舟 `doubao-embedding-vision-251215`；文档/查询分别设置检索指令，固定 1024 维。
- 每个子块独立调用多模态向量接口（不能把多个子块放在同一个 input 中融合成单向量）；限制并发、请求重试和批次超时。
- `rag/tool.py` 提供 Agent 检索工具，API 按短时授权校验用户和知识库，由 API 执行 pgvector + Elasticsearch BM25 双路召回与 RRF 融合，返回去重父块及引用；查询向量服务失败时继续发送原始查询以降级关键词检索。
- 向量与任务状态由 API 保存到 PostgreSQL/pgvector；仅 API 内部请求可调用分块/向量端点。
- 更换模型、维度或指令后需重新向量化；检索按向量空间 profile 过滤，不混用历史向量。
- 配置见 `.env.example` 的 `EMBEDDING_*` 与 `API_INTERNAL_URL`；密钥不返回前端。
