# LangSmith 离线评测

开发专用入口，不随 Sidecar 桌面程序打包。不新增产品页面，不改变生产会话存储。按 RAG、Agent / Harness、会议纪要三个板块组织，各自维护案例、运行目标与评分规则。当前包含 10 个仓库内合成案例：Agent / Harness 5 个、RAG 3 个、会议纪要 2 个。

## 安装与运行

在仓库根目录安装开发依赖：

```sh
services/sidecar/.venv/bin/python -m pip install -e './services/sidecar[eval]'
pnpm eval:smoke
```

| 命令                                           | 行为                                                                            |
| ---------------------------------------------- | ------------------------------------------------------------------------------- |
| `pnpm eval:smoke`                              | 使用固定模型替身和真实执行图/纪要格式校验，检查评测链路；不调用真实模型，不上传 |
| `pnpm eval:live`                               | 使用 Sidecar `.env` 的模型评测全部案例，产生模型调用；结果仅保存在本地          |
| `pnpm eval:live --suite agent`                 | 只评 Agent / Harness                                                            |
| `pnpm eval:live --suite rag`                   | 只评 RAG                                                                        |
| `pnpm eval:live --suite meetings`              | 只评会议纪要；兼容旧参数 `minutes`                                              |
| `pnpm eval:live --case agent-greeting-history` | 只检查“历史有旧任务时，问候是否误用工具”                                        |
| `pnpm eval:live --suite rag --judge`           | 在代码评分之外，额外调用同一模型进行语义评分                                    |
| `pnpm eval:live --upload`                      | 上传合成数据集、输出、评分和执行 trace 到 LangSmith                             |

`--repetitions 3` 可重复运行，范围 1–5。默认单并发，每例超时 90 秒、模型输出上限 2048 Token；可用 `--timeout`、`--max-tokens` 调整。模型 ID、地址、API Key 沿用 `.env` 的 `ARK_*`，不读取个人账号配置。

冒烟使用固定模型输出，**10/10 仅表示评测基础设施可用，不代表真实模型质量**。真实模型输出可变，评分失败应记录为基线，再决定调整提示词还是完善评分规则。

## LangSmith 配置

在 `services/sidecar/.env` 填写：

```dotenv
# LangSmith 评测上传凭证，不是方舟模型 API Key。
LANGSMITH_API_KEY=
# 美区默认地址；欧洲区或自托管按实际服务设置。
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
# 保持关闭；评测上传由显式 --upload 控制。
LANGSMITH_TRACING=false
```

只有 `--upload` 才创建 LangSmith 数据集和实验。每个板块单独建立数据集和实验，名称包含板块及案例内容指纹，重复运行复用相同案例版本；远程案例被改动时拒绝覆盖。实验记录模型、案例版本、Git 提交、提示词及评测代码指纹，方便对比改动前后表现。

本地模式同时设置 `upload_results=False`、关闭外层 tracing、客户端采样为 0，并使用无真实凭证的本地客户端；回归测试禁止所有 LangSmith HTTP 请求，即使外部 shell 开启 tracing 也不能上传。SDK 当前异步评测内部可能重新打开目标追踪，不能只依赖外层开关。

## 评测范围

- Agent：旧执行记录下的问候、致谢、实际创建文件、读取文件、敏感写入在审批前无副作用。
- RAG：固定检索结果下的有据回答、文档引用、资料缺失时拒绝编造、索引未就绪提示。使用合成 `search_knowledge` 工具夹具，**不评估 PG/ES/Embedding 的真实召回率或排名**；下一阶段需单独建立测试知识库和有标注文档 ID 的召回集。
- 会议：复用实际纪要生成提示词与格式校验，检查结论、行动项负责人/时间、未决事项；可用模型评分检查更细的语义准确性。
- 停止恢复、消息队列、隔离、幂等等确定性故障边界继续由现有 pytest 测试覆盖，不把固定模型替身的结果包装成真实模型评测。

评分用代码检查执行终态、工具白名单/必需工具、文件真实内容、审批前无写入、必要事实、引用与禁止断言。`--judge` 是辅助语义分，使用模型自身评分可能有偏差，应结合人工复核；工具安全与文件副作用始终由代码评分。当前文本包含检查对表达方式较敏感，后续可按真实失败案例扩展。

所有检查均单独记录。任一检查失败或目标异常，案例即失败，不能用平均质量分掩盖安全失败。退出码：0 全部通过，1 有失败案例，2 启动/配置/评测服务错误。

## 本地报告与数据边界

报告按板块保存在仓库 `.dp-work/evals/{rag,agent,meetings}/<UTC时间>-<随机后缀>.json`，包含每例输出、评分及失败状态，可供 CI 读取退出码。目录已由项目 `.dp-work` 忽略规则排除。

每个案例使用独立临时目录，完成后清理；命令执行被评测 Backend 禁用，不挂载用户项目、技能、连接器或长期记忆，不连接生产会议/知识库数据库。不从真实会话提取或自动上传测试数据。真实模型会收到仓库中的合成问题和资料；显式上传时这些合成输入、输出及 trace 会发送到配置的 LangSmith 服务。不要直接将案例替换为未经脱敏的业务数据。

## 目录与职责

```text
evals/
├── rag/                  # 文档命中、引用与无依据时的回答
│   ├── cases.json
│   ├── targets.py
│   └── evaluators.py
├── agent/                # Agent / Harness：工具、任务结果和审批
│   ├── cases.json
│   ├── targets.py
│   └── evaluators.py
├── meetings/             # 会议纪要：结论、行动项、负责人、时间
│   ├── cases.json
│   ├── targets.py
│   └── evaluators.py
├── common.py             # 隔离工作区、模型替身和共用评分辅助
├── registry.py           # 按板块加载案例、执行目标和评分规则
└── run.py                # 共用 LangSmith 运行与报告入口
```

每个板块的 `cases.json` 是输入及人工参考标准，`targets.py` 是实际运行入口，`evaluators.py` 是该板块的代码评分和语义评分标准。后续新增案例及规则应放在对应板块。

不传 `--suite` 时顺序运行全部板块，分别生成报告与 LangSmith 实验，最后输出总汇；单个板块失败不会被其他板块的通过分数掩盖。

| 板块            | 重点                                                 | 当前覆盖与边界                                                                                                                                      |
| --------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| RAG             | 文档能否检索到、引用正确、无答案时不编造             | 当前固定检索结果，已检查引用/拒答/索引未就绪；PG/ES 真实召回仍待接入                                                                                |
| Agent / Harness | 工具选择、任务完成、危险操作审批、停止恢复不重复执行 | 当前 LangSmith 案例覆盖前面三项；停止恢复及幂等继续由 `tests/agents/test_recovery.py`、`tests/sessions/test_session_recovery.py` 的实际执行测试覆盖 |
| 会议纪要        | 结论、行动项、负责人和时间准确，无遗漏或虚构         | 当前检查关键事实和结构，可通过该板块的语义评分标准辅助检查遗漏、分歧和虚构                                                                          |

参考：[离线评测](https://docs.langchain.com/langsmith/local)、[评测快速开始](https://docs.langchain.com/langsmith/evaluation-quickstart)。
