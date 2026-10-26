"""会议纪要 Markdown、BlockNote 块和 Yjs 状态转换。"""
from uuid import uuid4
from markdown_it import MarkdownIt
from pycrdt import Doc, XmlFragment, XmlElement, XmlText


def markdown_blocks(content):
    """将 Markdown 转成带嵌套关系的富文本块。"""
    from markdown_it.tree import SyntaxTreeNode
    tree = SyntaxTreeNode(MarkdownIt('commonmark').enable('table').parse(content))
    def inline(tokens):
        parts, styles, href = [], {}, None
        for token in tokens:
            mark = {'strong': 'bold', 'em': 'italic', 's': 'strike'}.get(token.type.rsplit('_', 1)[0])
            if token.type.endswith('_open') and mark: styles[mark] = True
            elif token.type.endswith('_close') and mark: styles.pop(mark, None)
            elif token.type == 'link_open': href = token.attrGet('href')
            elif token.type == 'link_close': href = None
            elif token.type in ('text', 'code_inline', 'softbreak', 'hardbreak'):
                value = '\n' if token.type.endswith('break') else token.content
                item = {'type': 'text', 'text': value, 'styles': {**styles, **({'code': True} if token.type == 'code_inline' else {})}}
                parts.append({'type': 'link', 'href': href, 'content': [item]} if href else item)
        return parts
    def convert(nodes):
        result = []
        for node in nodes:
            if node.type in ('bullet_list', 'ordered_list'):
                for item in node.children:
                    values = convert(item.children)
                    if not values: continue
                    first = values[0]
                    first['type'] = 'bulletListItem' if node.type == 'bullet_list' else 'numberedListItem'
                    first['children'].extend(values[1:])
                    result.append(first)
                continue
            if node.type == 'blockquote':
                values = convert(node.children)
                if values: values[0]['type'] = 'quote'
                result.extend(values)
                continue
            props, kind, value = {}, 'paragraph', []
            if node.type in ('heading', 'paragraph'):
                if node.type == 'heading': kind, props = 'heading', {'level': int(node.tag[1:])}
                for child in node.children:
                    if child.type == 'inline': value.extend(inline(child.token.children or []))
            elif node.type in ('fence', 'code_block'):
                kind, props = 'codeBlock', {'language': node.token.info.strip() or 'text'}
                value = [{'type': 'text', 'text': node.token.content.rstrip('\n'), 'styles': {}}]
            elif node.type == 'table':
                kind = 'table'
                rows = []
                for section in node.children:
                    for row in section.children:
                        cells = []
                        for cell in row.children:
                            values = []
                            for child in cell.children:
                                if child.type == 'inline': values.extend(inline(child.token.children or []))
                            cells.append(values)
                        rows.append({'cells': cells})
                value = {'type': 'tableContent', 'headerRows': 1, 'rows': rows}
            elif node.type == 'hr': kind = 'divider'
            else: continue
            result.append({'id': str(uuid4()), 'type': kind, 'props': props, 'content': value, 'children': []})
        return result
    return convert(tree.children) or [{'type': 'paragraph', 'content': []}]


def state_from_minutes(content, blocks=None):
    """保留已有富文本块，没有块数据时从 Markdown 初始化。"""
    formatted = []
    def inline_nodes(items):
        node = XmlText()
        chunks = []
        def collect(item, marks=None):
            marks = marks or {}
            if isinstance(item, str):
                chunks.append((item, marks))
            elif item.get('type') == 'link':
                for child in item.get('content', []): collect(child, {**marks, 'link': {'href': item.get('href', '')}})
            else:
                chunks.append((item.get('text', ''), {**marks, **{key: ({} if value is True else {'stringValue': value}) for key, value in item.get('styles', {}).items() if value is not False}}))
        for item in items if isinstance(items, list) else []: collect(item)
        formatted.append((node, chunks))
        return node
    def container(block):
        kind = block.get('type', 'paragraph')
        content = block.get('content', [])
        if kind == 'table' and isinstance(content, dict):
            rows = []
            for row_index, row in enumerate(content.get('rows', [])):
                cells = []
                for index, cell in enumerate(row.get('cells', [])):
                    cell_props = cell.get('props', {}) if isinstance(cell, dict) else {}
                    values = cell.get('content', []) if isinstance(cell, dict) else cell
                    width = (content.get('columnWidths') or [])[index:index + 1]
                    attrs = {**cell_props, 'colwidth': width or None}
                    tag = 'tableHeader' if row_index < content.get('headerRows', 0) or index < content.get('headerCols', 0) else 'tableCell'
                    cells.append(XmlElement(tag, attrs, [XmlElement('tableParagraph', {}, [inline_nodes(values)])]))
                rows.append(XmlElement('tableRow', {}, cells))
            node = XmlElement(kind, block.get('props', {}), rows)
        else:
            node = XmlElement(kind, block.get('props', {}), [inline_nodes(content)])
        children = [node]
        if block.get('children'):
            children.append(XmlElement('blockGroup', {}, [container(child) for child in block['children']]))
        return XmlElement('blockContainer', {'id': block.get('id') or str(uuid4())}, children)
    roots = [container(block) for block in (blocks or markdown_blocks(content))]
    doc = Doc({'document': XmlFragment([XmlElement('blockGroup', {}, roots)])})
    for node, chunks in formatted:
        for value, marks in chunks:
            node.insert(len(node), value, marks)
    return doc.get_update()


def minutes_from_state(state):
    """从已合并的 CRDT 导出富文本块和供导图、归档使用的 Markdown。"""
    doc = Doc(); doc.apply_update(state)
    root = doc.get('document', type=XmlFragment)
    def inline(node):
        values = []
        for child in node.children:
            if not isinstance(child, XmlText):
                continue
            for value, marks in child.diff():
                if not isinstance(value, str): continue
                marks = marks or {}
                styles = {key: (data.get('stringValue', True) if isinstance(data, dict) else data) for key, data in marks.items() if key != 'link'}
                item = {'type': 'text', 'text': value, 'styles': styles}
                link = marks.get('link')
                values.append({'type': 'link', 'href': link.get('href', ''), 'content': [item]} if isinstance(link, dict) else item)
        return values
    def blocks(group):
        result = []
        for container in group.children:
            if not isinstance(container, XmlElement) or container.tag != 'blockContainer': continue
            children = [child for child in container.children if isinstance(child, XmlElement)]
            node = next((child for child in children if child.tag != 'blockGroup'), None)
            if node is None: continue
            nested = next((child for child in children if child.tag == 'blockGroup'), None)
            content = inline(node)
            if node.tag == 'table':
                rows, header_rows, header_cols, widths = [], 0, 0, []
                for row_index, row in enumerate(node.children):
                    cells = []
                    if all(cell.tag == 'tableHeader' for cell in row.children): header_rows += 1
                    for col, cell in enumerate(row.children):
                        if row_index == 0:
                            widths.extend(cell.attributes.get('colwidth') or [None])
                            if cell.tag == 'tableHeader': header_cols += 1
                        paragraph = next(iter(cell.children), None)
                        attrs = dict(cell.attributes); attrs.pop('colwidth', None)
                        cells.append({'type': 'tableCell', 'props': attrs, 'content': inline(paragraph) if paragraph is not None else []})
                    rows.append({'cells': cells})
                content = {'type': 'tableContent', 'rows': rows, 'headerRows': header_rows, 'headerCols': 0 if header_rows else header_cols, 'columnWidths': widths}
            result.append({'id': container.attributes.get('id') or str(uuid4()), 'type': node.tag, 'props': dict(node.attributes), 'content': content, 'children': blocks(nested) if nested is not None else []})
        return result
    group = next((node for node in root.children if isinstance(node, XmlElement) and node.tag == 'blockGroup'), None)
    result = blocks(group) if group is not None else []
    def text(items):
        values = []
        for item in items:
            if item['type'] == 'link':
                values.append(f"[{text(item['content'])}]({item['href']})")
            else:
                value, styles = item['text'], item['styles']
                if styles.get('code'): value = f'`{value}`'
                if styles.get('bold'): value = f'**{value}**'
                if styles.get('italic'): value = f'*{value}*'
                if styles.get('strike'): value = f'~~{value}~~'
                values.append(value)
        return ''.join(values)
    def render(items, depth=0):
        lines = []
        for item in items:
            kind = item['type']
            if kind == 'table':
                rows = ['| ' + ' | '.join(text(cell.get('content', []) if isinstance(cell, dict) else cell).replace('|', '\\|').replace('\n', '<br>') for cell in row['cells']) + ' |' for row in item['content']['rows']]
                if rows: rows.insert(1, '| ' + ' | '.join('---' for _ in item['content']['rows'][0]['cells']) + ' |')
                lines.append('\n'.join(rows))
                continue
            value = text(item['content'])
            if kind == 'heading': value = '#' * max(1, min(6, int(item['props'].get('level', 1)))) + ' ' + value
            elif kind in ('bulletListItem', 'numberedListItem', 'checkListItem'):
                prefix = '1. ' if kind == 'numberedListItem' else ('- [x] ' if item['props'].get('checked') else '- [ ] ') if kind == 'checkListItem' else '- '
                value = '  ' * depth + prefix + value
            elif kind == 'quote': value = '> ' + value
            elif kind == 'divider': value = '---'
            elif kind in ('image', 'file', 'video', 'audio'): value = f"[{item['props'].get('name', kind)}]({item['props'].get('url', '')})"
            elif kind == 'codeBlock': value = f"```{item['props'].get('language', '')}\n{value}\n```"
            lines.append(value)
            if item['children']: lines.append(render(item['children'], depth + 1))
        return '\n\n'.join(lines)
    return render(result), result
