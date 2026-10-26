# 知识库处理

- `parsers/pdf.py`：PyMuPDFLoader 提取 PDF 正文和 Markdown 表格，逐页保存页码，不启用 OCR 或图片识别。
- `parsers/word.py`：python-docx 按顺序提取 DOCX 标题、段落、列表和普通表格，生成 Markdown 与 BlockNote 块；旧版 DOC、图片及复杂排版暂不处理。
- `parsers/text.py`：TXT 与 Markdown 以 UTF-8 读取，统一换行并清理无效控制字符，Markdown 保留原有结构。
- `parsers/dispatcher.py`：独立子进程执行 PDF 解析，超时和取消时结束进程并清理临时文件；TXT、Markdown 使用 LangChain TextLoader 读取，DOCX 使用独立子进程执行。
- 内部接口 `POST /internal/knowledge/parse`：API 使用内部凭证发送文件字节和 `file_type`（pdf / txt / md / docx），在线文档发送已保存的正文，无需共享文件系统。
- 限制：文件最大 20 MB、提取正文最大 8 MB；PDF 最多 200 页，PDF 子进程超时由 `PDF_PARSE_TIMEOUT` 控制。
- 解析结果包含 `content`、来源 `metadata`（PDF 含页码）、`parser`，任务和结果由 API 存入 PostgreSQL。
- 解析结果支持前端人工修订；分块、Embedding、向量索引与检索尚未接入。后续检索入口可封装为 Agent 的知识库检索 Tool。
