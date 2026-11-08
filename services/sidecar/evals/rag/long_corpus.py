"""以官方 API 正文和相邻上下文构建 100 篇实际 2–3 页的文字 PDF。"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .web_files import make_pdf


def entries(source):
    result = {}
    soup = BeautifulSoup(source.read_bytes(), 'html.parser')
    for original in soup.select('dl.py'):
        entry = BeautifulSoup(str(original), 'html.parser').find('dl')
        signature, detail = entry.find('dt', recursive=False), entry.find('dd', recursive=False)
        if not signature or not signature.get('id') or not detail:
            continue
        for node in detail.select('dl.py'):
            node.decompose()
        for node in entry.select('.headerlink, .viewcode-link'):
            node.decompose()
        blocks = []
        for node in detail.find_all(recursive=False):
            pre = node if node.name == 'pre' else node.find('pre')
            text = '```python\n' + pre.get_text().strip() + '\n```' if pre else node.get_text(' ', strip=True)
            blocks.append(text)
        blocks = [block for block in blocks if block]
        result[signature['id']] = [signature.get_text(' ', strip=True), *blocks]
    return result


def generate(sources, output, questions, font):
    output.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('WebChinese', str(font), subfontIndex=0))
    rows = [line.split('|', 2) for line in questions.read_text().splitlines() if line.strip()]
    # TOML 模块原始全文不足两页，不用重复正文补足长度。
    rows = [row for row in rows if row[0] != 'tomllib']
    rows = [rows[round(i * (len(rows) - 1) / 99)] for i in range(100)] if len(rows) >= 100 else rows
    if len(rows) != 100:
        raise ValueError('需要 100 条场景问题')
    modules = {slug: entries(sources / (slug + '.html')) for slug in dict.fromkeys(row[0] for row in rows)}
    docs, queries = [], []
    for slug, anchor, question in rows:
        units = modules[slug]
        key = 'long-' + hashlib.sha256((slug + '#' + anchor).encode()).hexdigest()[:16]
        target = output / (key + '.pdf')
        source = sources / (slug + '.html')
        doc = dict(id=key, title=anchor + '：接口与相关上下文',
            source_url=f'https://docs.python.org/zh-cn/3.14/library/{slug}.html#{anchor}',
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            file_type='pdf', variant='pdf_text', filename=target.name, excerpt=True,
            source_anchors=[anchor], complete_anchors=[], expected_fragments=[anchor])
        blocks = list(units[anchor])
        last_page_characters = 0
        def render():
            nonlocal last_page_characters
            doc['content'] = '\n\n'.join(blocks)
            make_pdf(doc, target)
            with pymupdf.open(target) as pdf:
                last_page_characters = len(pdf[-1].get_text().strip())
                return len(pdf)
        pages = render()
        # 过长条目按完整 HTML 块节选，不重复正文或人为扩大字号。
        while pages > 3 and len(blocks) > 2:
            blocks.pop()
            pages = render()
        if pages > 3:
            raise ValueError('单个段落过长：' + anchor)
        if blocks == units[anchor]:
            doc['complete_anchors'].append(anchor)
        # 优先相邻接口，保留完整段落；达到两页即停止补充。
        names = list(units)
        index = names.index(anchor)
        neighbors = sorted((name for name in names if name != anchor), key=lambda name: abs(names.index(name) - index))
        for neighbor in neighbors:
            if pages >= 3 or (pages == 2 and last_page_characters >= 600):
                break
            before = len(blocks)
            blocks.extend(units[neighbor])
            candidate_pages = render()
            if candidate_pages <= 3:
                pages = candidate_pages
                doc['source_anchors'].append(neighbor)
                doc['complete_anchors'].append(neighbor)
            else:
                del blocks[before:]
                # 仅补充能容纳的完整段落，不把整个长章节硬塞进来。
                added = 0
                for block in units[neighbor]:
                    blocks.append(block)
                    candidate_pages = render()
                    if candidate_pages > 3:
                        blocks.pop()
                        break
                    added += 1
                    pages = candidate_pages
                    if pages >= 3 or (pages == 2 and last_page_characters >= 600):
                        break
                if added:
                    doc['source_anchors'].append(neighbor)
                pages = render()
        if not 2 <= pages <= 3:
            raise ValueError(f'{anchor}: {pages} 页，缺少足够的原始上下文')
        doc.update(pages=pages, last_page_characters=last_page_characters, characters=len(doc['content']), file_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        docs.append(doc)
        queries.append(dict(id=key + '-query', group='scenario', question=question, target_anchor=anchor,
            target_module=slug, relevant_document_ids=[key]))
        print(f'{len(docs)}/100 {anchor}: {pages} 页 / {doc["characters"]} 字符', flush=True)
    # 完整包含同一接口的上下文文档也标为相关，减少重叠语料造成的假阴性。
    for query in queries:
        for doc in docs:
            if doc['source_url'].split('#')[0].endswith('/' + query['target_module'] + '.html') and query['target_anchor'] in doc['complete_anchors']:
                if doc['id'] not in query['relevant_document_ids']:
                    query['relevant_document_ids'].append(doc['id'])
        query['annotation'] = 'Scenario drafted independently of source phrasing; anchor-based labels include complete overlapping entries; pending human answer-level review'
    shutil.copyfile(sources / 'LICENSE.html', output / 'SOURCE_LICENSE.html')
    manifest = dict(version=5, synthetic=False, origin='official-python-docs', file_set='python-long-100-v1',
        created_at=datetime.now(timezone.utc).isoformat(),
        query_origin='100 assistant-authored non-template scenario questions; not human-reviewed; anchor-based draft labels',
        limitations='100 topic excerpts derived from cached official module pages, not 100 independent original publications; neighboring context overlaps; anchor labels are not exhaustive answer judgments; long entries excerpted at whole HTML blocks; no reranker',
        documents=docs, queries=queries)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print('完成 100 篇 2–3 页 PDF、100 条场景问题。', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--questions', type=Path, default=Path(__file__).with_name('long_questions.tsv'))
    parser.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/STHeiti Light.ttc'))
    args = parser.parse_args()
    generate(args.sources, args.output, args.questions, args.font)
