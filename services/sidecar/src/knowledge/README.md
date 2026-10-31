# 知识库处理

- `parsers/pdf.py`：PyMuPDFLoader 提取 PDF 正文和 Markdown 表格，无文字层且含图片/绘制内容的页面自动使用百度 OCR，逐页保存页码；空白页不调用 OCR。
- `providers/ocr/baidu.py`：百度通用文字识别高精度版（`accurate_basic`）；按解析任务复用令牌，令牌失效只刷新一次。扫描页识别失败则整个解析失败，不保存缺页结果。
- `parsers/word.py`：python-docx 按顺序提取 DOCX 标题、段落、列表和普通表格，生成 Markdown 与 BlockNote 块；旧版 DOC、图片及复杂排版暂不处理。
- `parsers/text.py`：TXT 与 Markdown 以 UTF-8 读取，统一换行并清理无效控制字符，Markdown 保留原有结构。
- `parsers/dispatcher.py`：独立子进程执行 PDF 解析，超时和取消时结束进程并清理临时文件；TXT、Markdown 使用 LangChain TextLoader 读取，DOCX 使用独立子进程执行。
- RPC `knowledge.parse`：API 经设备链路发送文件字节和 `file_type`（pdf / txt / md / docx），在线文档发送已保存的正文，无需共享文件系统。
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

## PDF 扫描页 OCR

在 Sidecar `.env` 配置 `BAIDU_OCR_API_KEY`、`BAIDU_OCR_SECRET_KEY`，百度控制台需开通通用文字识别高精度版。仅扫描页图像发送给百度；普通文字页不发送，也不产生 OCR 调用。

默认单请求超时 20 秒、每个 PDF 最多识别 20 页，可通过 `BAIDU_OCR_TIMEOUT_SECONDS`、`BAIDU_OCR_MAX_PAGES` 调整。整个任务仍受 `PDF_PARSE_TIMEOUT` 和上游任务超时限制；大文件建议拆分。额度、权限、限流、超时会给出可展示错误，沿用已有任务失败通知和手动重试。

OCR 输出为按行文本，保留源页码，扫描页标记 `extraction_method=baidu_ocr`；不是表格结构或版面还原。当前不识别已有文字层页面内部的插图文字，也不支持单独上传图片。原文件不变，解析结果继续支持编辑、自动保存和向量化。

接口依据：[通用文字识别](https://ai.baidu.com/tech/ocr/general)、[鉴权说明](https://ai.baidu.com/ai-doc/REFERENCE/Ck3dwjhhu)。
