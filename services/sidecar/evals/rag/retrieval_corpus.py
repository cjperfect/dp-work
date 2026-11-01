"""可复现的合成检索语料：10 个相似产品、每个 3 篇文档，共 70 个标注查询。"""


def build_corpus():
    """用固定业务事实构造型号区分、语义改写和跨文档检索场景。"""
    products = [
        ('N6mini', '掌心便携按摩仪', 1800, 90, 12, '干布擦拭', '红灯连续闪烁'),
        ('N6pro', '深层肌肉按摩仪', 2600, 120, 18, '微湿软布擦拭后晾干', '电机温度过高'),
        ('N6max', '运动恢复按摩仪', 3200, 150, 24, '拆下硅胶头单独清洗', '机身持续震动异常'),
        ('K2mini', '便携颈部放松仪', 1200, 60, 12, '酒精棉片仅擦接触电极', '电极接触提示音重复'),
        ('K2pro', '办公颈肩热敷仪', 2200, 100, 18, '断电后用干布清洁热敷面', '热敷区域局部过热'),
        ('K2max', '家用颈肩护理仪', 3600, 180, 24, '取下布套手洗并自然晾干', '屏幕显示E03'),
        ('E3mini', '旅行眼部舒缓仪', 1000, 50, 6, '一次性清洁片擦拭眼罩', '气囊无法完全放气'),
        ('E3pro', '睡前眼部热敷仪', 2000, 80, 12, '可拆洗内衬低温手洗', '语音提示压力异常'),
        ('F5mini', '轻便足部放松仪', 2800, 130, 18, '足垫拆下后中性清洁剂清洗', '转轮卡滞并发出异响'),
        ('F5pro', '家用足部护理仪', 4800, 200, 36, '内胆取下单独手洗', '气压长时间不释放'),
    ]
    docs, queries = [], []
    for model, alias, battery, minutes, warranty, cleaning, fault in products:
        facts = {
            'spec': ('规格与续航', f'电池容量为 {battery}mAh，标准模式续航约 {minutes} 分钟。充电采用 USB-C 接口，额定输入 5V/2A。',
                     f'{model} 的电池容量是多少？', f'出差带的{alias}用多大电池、充满电能工作多久？', ['电池容量', '续航']),
            'care': ('清洁与故障处理', f'清洁方式：{cleaning}。若出现“{fault}”，应立即停机并断开电源，联系售后，不得自行拆机。',
                     f'{model} 应如何清洁？', f'{alias}出现{fault}时该怎么处理？', ['清洁', '故障']),
            'warranty': ('保修与售后', f'整机保修 {warranty} 个月，从购买凭证日期起计算。报修需提供序列号、购买凭证和故障视频。人为进水、跌落及擅自拆机不在免费保修范围内。',
                         f'{model} 的保修期限是几个月？', f'{alias}报修需要准备哪些材料，自己拆开后还能免费保修吗？', ['保修', '报修材料']),
        }
        for kind, (topic, fact, direct, paraphrase, headings) in facts.items():
            key = f'{model.lower()}-{kind}'
            title = f'{model} {topic}'
            content = (f'# {title}\n\n本文件为合成评测资料，不代表真实产品参数。'
                       f'本页适用于 {model}，产品名称为{alias}，不适用于其他型号。\n\n'
                       f'## {headings[0]}与{headings[1]}\n\n{fact}\n\n'
                       f'使用前请核对机身型号；相同系列不同版本的规格、维护方法及保修期限可能不同。'
                       f'本文件只作为 {model} 的{topic}依据，其他主题请查对应文档。')
            docs.append({'id': key, 'title': title, 'content': content})
            for group, question in [('exact', direct), ('paraphrase', paraphrase)]:
                queries.append({'id': f'{key}-{group}', 'group': group, 'question': question,
                                'relevant_document_ids': [key]})
    # 每个型号与下一型号对比，两个来源都召回才算完整；不只统计“任意命中”。
    for index, product in enumerate(products):
        first, second = product[0], products[(index + 1) % len(products)][0]
        queries.append({'id': f'compare-{index + 1}', 'group': 'multi_document',
                        'question': f'比较 {first} 和 {second} 的电池容量与续航时间，分别是多少？',
                        'relevant_document_ids': [first.lower() + '-spec', second.lower() + '-spec']})
    return {'version': 1, 'synthetic': True, 'documents': docs, 'queries': queries}
