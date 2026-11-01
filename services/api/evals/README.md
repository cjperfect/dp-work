# 真实检索评测

仓库根目录执行 `pnpm eval:retrieval`。使用 Sidecar 的 Markdown Loader、父子分块及真实方舟 Embedding，再使用 API 的 pgvector、Elasticsearch BM25 和 RRF 检索实现，对比纯向量、纯关键词、混合检索三种模式。不使用 BGE Reranker。

语料在 `services/sidecar/evals/rag/retrieval_corpus.py`：10 个相近型号，每个型号包含规格、清洁故障、保修三个主题，共 30 篇合成 Markdown 文档。70 个查询中，精确问题 30 条、语义改写 30 条、双文档对比 10 条。相关文档 ID 显式标注，不让模型给自己的检索结果评分。

配置沿用 API 的 PostgreSQL、Elasticsearch 连接，以及 Sidecar 的 `EMBEDDING_*`。会产生真实向量服务调用费用，文档和问题都是合成数据。程序创建随机命名的 `dp_work_eval_*` 数据库与 `dp-work-eval-*` 索引，结束时清理；数据库账号需要创建数据库及 vector 扩展权限。从不在应用数据库写入评测记录，不启动 MQ，也不创建用户实际可登录的账号。

数据与报告默认保存在 `.dp-work/evals/rag/retrieval-30/`：

- `documents/`：30 篇可查看的 Markdown 文档。
- `corpus.json`：语料、问题与相关文档标签。
- `prepared.json`：真实文档/查询向量与父子块缓存，相同语料和向量空间可复用。
- `report-*.json`：模型配置、语料指纹、分组统计、逐题排名、指标和检索耗时。

`pnpm eval:retrieval --prepared` 跳过向量准备；首次运行不要使用该参数。更改解析或分块代码后应删除 `prepared.json` 重新准备。无需重新运行真实模型时，保留缓存即可复测检索代码。

## 指标口径

按生产链路实际返回的前 5 个父块按文档去重，计算文档级宏平均指标；不是先取大量结果再挑 5 篇文档。双文档问题的 Recall 按两个相关文档计算，不用“任意命中”替代。

- Recall@5：前五条结果覆盖的相关文档数 / 全部相关文档数。
- MRR@5：首个相关文档的排名倒数，未命中计 0。
- nDCG@5：二元相关性下的归一化排序质量。
- Precision@5：相关文档数 / 5；大多数问题只有一个相关文档，不能期待该指标达到 100%。
- Hit@5：至少命中一个相关文档的问题比例。
- P50 / P95：只统计查询向量已经准备好的检索阶段，不包括 Embedding 请求时间，不是端到端回答耗时。

服务降级或关键词索引未同步时直接终止，不将降级结果记为混合检索。当前不测上传、MQ 调度、OCR、最终回答准确率、拒答或引用忠实度；这些需要各自的质量/集成评测。

这是开发用小型合成集，结果不应外推为真实企业文档准确率，也不证明 BGE 精排有效。增加真实脱敏文档、人工标签及困难负例后，应作为新测试集单独报告。

## 混合 PDF / Markdown 语料

`services/sidecar/evals/rag/mixed_files.py` 可将同一组事实生成 10 篇 Markdown、10 篇文字型 PDF、5 篇扫描 PDF、5 篇流程图扫描 PDF。运行时需要开发依赖 `reportlab`、系统 `pdftoppm` 以及支持中文的 TrueType 字体；不增加生产 Sidecar 依赖。生成文件的 SHA256 写入清单，扫描 PDF 只嵌入页图，不附隐藏文字层。

在 Sidecar 目录生成（`python` 使用安装了 reportlab 的开发解释器）：

```sh
python -m evals.rag.mixed_files ../../.dp-work/evals/rag/retrieval-mixed-30/files --font /实际路径/中文字体.ttf
```

回到仓库根目录执行：

```sh
pnpm eval:retrieval --output ../../.dp-work/evals/rag/retrieval-mixed-30 --files ../../.dp-work/evals/rag/retrieval-mixed-30/files
```

注意：该命令在 `services/api` 工作目录解析相对参数，因此上面的 `../../.dp-work` 指向仓库数据目录；也可以全部使用绝对路径。已有缓存复跑时使用相同 `--output` 加 `--prepared`。

解析直接读取真实 PDF / MD 文件，PDF 经过原解析子进程和百度 OCR，只有实际提取结果进入分块、向量与索引，清单里的参考正文不参与召回。解析代码或源文件改变会使准备缓存失效。报告新增格式分组、OCR 页数及预先标注关键文本的遗漏检查，解析后的正文保存在 `documents/`，源文件与预览保存在 `files/`。

关键文本检查不等于全文 OCR 字符准确率；包含流程图的测试只测图中节点文字能否进入检索，不测箭头关系、分支条件或执行顺序理解。70 个问题与纯 Markdown 集一致，因此不会用不同问题集混淆格式变化与检索效果的差异。

## 网络真实文档集

`services/sidecar/evals/rag/web_files.py` 从固定的 Python 3.14 官方中文文档地址采集 30 个主题，保留完整段落、代码与目标 API 上下文，并明确标注为章节节选。每篇保存来源 URL、章节锚点、原始 HTML 指纹和下载时间，PSF 许可页保存在 `_sources/LICENSE.html`；不使用模型编造正文。该开发脚本额外需要 beautifulsoup4、markdownify、reportlab 和 Poppler。

生成器输出 15 篇 MD、12 篇文字 PDF、3 篇扫描 PDF（扫描版由官方文字原页栅格化产生，非原站扫描件）。真实网络资料与先前的短合成产品集是两个独立数据集，不直接比较分数；新的 70 条问题按实际 API 和章节重新标注，包含精确查询、语义改写、跨文档组合。标签为开发者标注，仍需业务专家复核及后续补充真实问题。

在 Sidecar 目录运行：

```sh
python -m evals.rag.web_files ../../.dp-work/evals/rag/retrieval-web-30/files --font /实际路径/中文字体.ttf
```

在仓库根目录测试已有文件：

```sh
pnpm eval:retrieval --output ../../.dp-work/evals/rag/retrieval-web-30 --files ../../.dp-work/evals/rag/retrieval-web-30/files
```

报告 `synthetic=false`、`origin=official-python-docs`，可据此区别于合成产品集。文件里没有复制问题或参考答案；只有实际解析结果进入索引。该集不评估流程图关系理解，也未建立 OCR 全文字符级标注，空的逐字锚点列表不能解释为 OCR 零错误。
