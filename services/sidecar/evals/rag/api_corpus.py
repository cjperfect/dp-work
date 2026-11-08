"""从缓存官方 HTML 中生成 100 篇 API 节选与弱标注问题。"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from markdownify import markdownify


def generate(sources, output, count=100):
    output.mkdir(parents=True, exist_ok=True)
    if (sources / 'LICENSE.html').exists():
        shutil.copyfile(sources / 'LICENSE.html', output / 'SOURCE_LICENSE.html')
    groups = []
    for source in sorted(sources.glob('*.html')):
        if source.stem == 'LICENSE':
            continue
        candidates = []
        for original in BeautifulSoup(source.read_bytes(), 'html.parser').select('dl.py'):
            entry = BeautifulSoup(str(original), 'html.parser').find('dl')
            signature, detail = entry.find('dt', recursive=False), entry.find('dd', recursive=False)
            if not signature or not signature.get('id') or not detail:
                continue
            for node in detail.select('dl.py'):
                node.decompose()
            for node in entry.select('.headerlink, .viewcode-link'):
                node.decompose()
            paragraph = detail.find('p', recursive=False)
            description = paragraph.get_text(' ', strip=True) if paragraph else ''
            text = markdownify(str(entry), heading_style='ATX').strip()
            if 180 <= len(text) <= 10000 and len(description) >= 20:
                candidates.append((signature['id'], text, description, source))
        if candidates:
            groups.append(candidates)
    selected = []
    for index in range(max(map(len, groups), default=0)):
        for group in groups:
            if index < len(group):
                selected.append(group[index])
                if len(selected) == count:
                    break
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f'只有 {len(selected)} 个条目，不足 {count}')
    documents, queries = [], []
    for index, (anchor, text, description, source) in enumerate(selected):
        key = 'api-' + hashlib.sha256((source.stem + '#' + anchor).encode()).hexdigest()[:16]
        url = f'https://docs.python.org/zh-cn/3.14/library/{source.stem}.html#{anchor}'
        file = output / (key + '.md')
        file.write_text(f'# {anchor}\n\n{text}\n\n来源：{url}\n许可：PSF License Version 2\n', encoding='utf-8')
        documents.append(dict(id=key, title=anchor, filename=file.name, file_type='md', variant='md',
            source_url=url, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            file_sha256=hashlib.sha256(file.read_bytes()).hexdigest(), expected_fragments=[], excerpt=True))
        exact = index % 2 == 0
        question = f'Python 中 {anchor} 的用途、参数与使用方法是什么？' if exact else f'Python 中需要完成以下功能，应使用什么接口、如何使用？{description}'
        queries.append(dict(id=key + '-query', group='exact' if exact else 'source_description', question=question,
            relevant_document_ids=[key], annotation='API anchor target; generated weak labels, requires human review'))
    manifest = dict(version=4, synthetic=False, origin='official-python-docs', file_set='python-api-100-v1',
        created_at=datetime.now(timezone.utc).isoformat(),
        query_origin='50 API-name templates + 50 source-description templates; weak labels, not independent human paraphrases',
        limitations='100 API excerpts from cached module pages; description questions reuse source wording; similar API relevance labels may be incomplete; no reranker',
        documents=documents, queries=queries)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f'已生成 {len(documents)} 篇文档、{len(queries)} 条问题，来自 {len({row[3].stem for row in selected})} 个模块页面。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    generate(args.sources, args.output)
