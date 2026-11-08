"""合成诊断集：用相近标识符和语义改写观察检索策略差异，不估计业务收益。"""
import argparse
import hashlib
import json
from pathlib import Path

NOTICE = '本文件是虚构的检索诊断案例，不代表真实产品、错误码或公司制度。'


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    docs, queries = [], []

    def document(key, title, body):
        content = f'# {title}\n\n{NOTICE}\n\n{body}\n'
        target = output / (key + '.md')
        target.write_text(content)
        docs.append(dict(id=key, title=title, content=content, filename=target.name,
            file_type='md', variant='md', file_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))

    def query(key, group, question, expected):
        queries.append(dict(id=key + '-q', group=group, question=question,
            relevant_document_ids=[key], expected_answer=expected,
            annotation='Explicit fictional facts; draft labels; diagnostic rather than representative workload'))

    for i in range(16):
        model = f'BX202-{"A" if i < 8 else "B"}{i % 8 + 1}'
        capacity, minutes = 1400 + i * 120, 65 + i * 7
        key = f'model-{i:02d}'
        document(key, f'{model} 便携按摩仪规格',
            f'## 适用范围\n\n本页仅适用于机身铭牌型号 {model}。同系列外观相近，不能根据颜色判断型号。\n\n'
            f'## 电池与续航\n\n{model} 的电芯标称容量为 {capacity}mAh，标准档可连续运转约 {minutes} 分钟。'
            '采用 USB-C 充电，额定输入 5V/2A；高强度档运行时间会缩短。\n\n'
            '## 使用说明\n\n首次使用前充满电，充电期间不要运行电机。核对完整型号后再查对应规格，不沿用相邻后缀型号的数据。')
        if i % 2 == 0:
            query(key, 'model_identifier', f'{model} 的电池容量和标准档续航分别是多少？', f'{capacity}mAh；{minutes} 分钟')

    codes = ['K7Q9', 'K7Q8', 'K7P9', 'K8Q9', 'M2R6', 'M2R8', 'M3R6', 'N2R6',
             'X9A1', 'X9A7', 'X8A1', 'Y9A1', 'T4C2', 'T4C3', 'T5C2', 'U4C2']
    actions = ['刷新租户签名后重试', '重新同步设备时间', '重新绑定设备证书', '申请新的客户端凭据',
               '刷新部门授权快照', '清除已吊销的访问令牌', '重建用户身份映射', '重新获取组织会话',
               '修复租户请求头', '切换到正确的服务区域', '补充缺失的设备指纹', '更新服务账户密钥',
               '解除账户临时冻结', '重新授权知识库范围', '校正回调签名算法', '更新客户端信任列表']
    for i, (suffix, action) in enumerate(zip(codes, actions, strict=True)):
        code = 'ERR_AUTH_' + suffix
        key = f'error-{i:02d}'
        document(key, f'{code} 接入故障处理单',
            f'## 现象\n\n云端执行网关返回 {code}，请求未进入业务处理。界面可能只显示“认证失败，请重试”。\n\n'
            f'## 恢复步骤\n\n此错误的对应处理动作是：{action}。完成后发起一次探测请求，并核对原请求的跟踪编号。'
            f'只有错误代码完全等于 {code} 时才使用本单；近似代码需要打开对应处理单。\n\n'
            '## 排查记录\n\n保留发生时间、设备编号和跟踪编号，不保存明文密钥。反复提交原请求不能替代修复认证配置。')
        if i % 2 == 0:
            query(key, 'error_identifier', f'请求返回 {code}，对应的恢复动作是什么？', action)

    versions = ['2.3.0', '2.3.1', '2.3.2', '2.3.9', '2.13.0', '2.13.1', '2.30.0', '2.30.1',
                '3.2.0', '3.2.1', '3.12.0', '3.12.1', '3.20.0', '3.20.1', '3.21.0', '3.21.1']
    for i, version in enumerate(versions):
        key = f'version-{i:02d}'
        limit, field = 20 + i * 5, f'resume_marker_{i+1:02d}'
        document(key, f'DocSync {version} 批量同步协议',
            f'## 协议版本\n\n本文对应 DocSync {version}，调用方应先核对响应头中的完整版本。'
            '补丁版和次版本的批量参数可能不同。\n\n'
            f'## 请求约束\n\nDocSync {version} 单次最多接收 {limit} 个文档。超过限制应拆成多批。'
            f'中断后继续同步时，读取响应字段 {field} 并在下一次调用中原样回传。\n\n'
            '## 校验流程\n\n先在测试项目提交一批文档，核对接收条数与继续标记。不要把其他版本的限制值和字段名混入当前请求。')
        if i % 2 == 0:
            query(key, 'version_identifier', f'DocSync {version} 一批能提交多少文档，续接字段叫什么？', f'{limit}；{field}')

    scenarios = [
        ('幂等消费', '以业务流水号建立唯一约束，已成功处理的流水直接返回原结果，不重复写入交易。', '支付平台把同一笔成功通知推了两遍，怎样保证系统只记一笔账？'),
        ('事务消息', '在同一数据库事务中写业务记录与待投递事件，后台扫描未投递事件并发送到消息队列。', '订单已经保存了，但机器突然断电，下游没收到通知，怎样避免这件事被彻底漏掉？'),
        ('租约回收', '工作进程领取任务时登记有效期，处理期间续期，过期且未完成的任务可以由其他进程重新领取。', '处理任务的那台机器突然没了，如何让别的机器接着处理，而不是一直等它？'),
        ('结果版本校验', '每次生成记录递增修订号，结果写回时核对修订号；只接受与当前任务修订一致的输出。', '用户改完内容后又生成了一次，但上一次的慢请求最后才回来，怎样保住新内容？'),
        ('上下文压缩', '保留当前目标、关键决策和未完成事项，将较早的工具输出整理成摘要后移出活跃上下文。', '机器人聊久了总是超长，怎样减少它要读的历史内容，同时记住做到哪里了？'),
        ('权限范围过滤', '查询时依据当前身份与已授权资源集合过滤候选数据，检索、引用和详情接口使用一致的资源范围。', '两个部门都用了同一个助手，怎样防止一个部门问到另一个部门的内部资料？'),
        ('人工审批挂起', '遇到删除、发布等高风险工具调用时先保存执行检查点并挂起，等待授权后从该调用继续。', '机器人准备删除一批文件，怎样让它先等负责人点头，再接着往下做？'),
        ('指数退避', '面对可恢复的短暂失败，限制重试总次数并逐步增加等待间隔，加入随机抖动以分散同时重试。', '外部接口突然繁忙，很多请求一起再次发送又挤爆了，怎样让大家错开再试？'),
        ('失败告警', '连续失败达到阈值后通知值班人员，附上任务标识与追踪信息，由值班人员判断故障范围。', None),
        ('并发隔离', '为不同任务类别设置独立的并发配额，防止耗时任务占满所有执行位置。', None),
        ('上下文窗口扩容', '选择支持更长输入窗口的模型，允许单次传入更多历史消息，同时评估输入成本与响应耗时。', None),
        ('前端按钮隐藏', '根据角色权限决定是否渲染操作按钮，未授权用户看不到对应入口，后端仍需独立执行鉴权。', None),
        ('进程取消', '对用户明确中止的任务发送取消信号，并在工具调用边界检查取消状态，终止后续执行。', None),
        ('历史版本恢复', '从版本列表选择某次快照，将旧正文作为一次新的修订写入，不删除后续修订记录。', None),
        ('查询缓存', '对同一向量空间下的相同查询复用短期查询向量，缓存超时或模型配置改变后重新计算。', None),
        ('任务预算', '为每次执行设置费用与工具调用次数上限，到达预算后停止扩展新步骤并向用户说明当前进展。', None),
    ]
    for i, (topic, fact, question) in enumerate(scenarios):
        key = f'semantic-{i:02d}'
        document(key, f'Agent 平台工程方案：{topic}',
            f'## 方案\n\n{fact}\n\n## 验证\n\n通过正常路径与对应的异常路径验证此机制，'
            '记录输入条件、状态变化和输出结果。该方案解决当前主题的问题，不替代其他可靠性或安全控制。')
        if question:
            query(key, 'semantic_paraphrase', question, fact)

    manifest = dict(version=1, synthetic=True, origin='synthetic-diagnostic', file_set='identifier-semantic-contrast-v1',
        query_origin='Assistant-authored fictional diagnostic documents and scenario questions; not human-reviewed',
        limitations='Purpose-built contrast cases with identifier near-misses and paraphrases; not a representative enterprise benchmark; all facts fictional; no reranker; do not infer production uplift',
        documents=docs, queries=queries)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f'已生成 {len(docs)} 篇合成诊断文档、{len(queries)} 条问题。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
