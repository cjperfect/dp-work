"""采集有开放许可的 Python 官方中文章节，生成真实内容 PDF/MD 检索集。"""
import argparse
import concurrent.futures
import hashlib
import html
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

BASE = 'https://docs.python.org/zh-cn/3.14/'
SPECS = [
    ('json', ['json.dump', 'json.loads'], 'json.dump 的 ensure_ascii 参数控制什么？', '把包含中文的对象写成 JSON 时，怎样避免汉字变成转义序列？'),
    ('csv', ['csv.reader', 'csv.DictReader'], 'csv.DictReader 如何确定字段名？', '读取带表头的逗号分隔文件，怎样让每一行按列名取值？'),
    ('configparser', ['quick-start', 'supported-datatypes'], 'ConfigParser 支持哪些读取配置值的数据类型方法？', 'INI 文件中的开关和数字读取后如何转成布尔值和整数？'),
    ('argparse', ['argumentparser-objects', 'the-add-argument-method'], 'ArgumentParser 的 add_argument 如何定义命令行参数？', '怎样在命令行程序里定义选项并自动生成帮助信息？'),
    ('logging', ['logging.basicConfig', 'logging.getLogger'], 'logging.basicConfig 的 force 参数有什么作用？', '程序已有日志处理器时，怎样重新应用基础日志配置？'),
    ('logging.handlers', ['logging.handlers.RotatingFileHandler', 'logging.handlers.TimedRotatingFileHandler'], 'RotatingFileHandler 的 maxBytes 和 backupCount 分别控制什么？', '日志文件越来越大，如何限制大小并保留固定数量的旧文件？'),
    ('pathlib', ['pathlib.Path.read_text', 'pathlib.Path.write_text'], 'Path.read_text 如何指定编码读取文件？', '使用面向对象的路径接口，如何将文本写入文件并读取回来？'),
    ('shutil', ['shutil.copytree', 'shutil.ignore_patterns'], 'shutil.copytree 如何使用 ignore 参数排除文件？', '复制整个目录时，怎样跳过缓存目录和临时文件？'),
    ('tempfile', ['tempfile.TemporaryDirectory', 'tempfile.NamedTemporaryFile'], 'TemporaryDirectory 如何自动清理临时目录？', '一段处理完成后希望中间文件自动删除，应如何管理临时目录？'),
    ('sqlite3', ['tutorial'], 'sqlite3 的 SQL 查询怎样使用占位符绑定参数？', '把用户输入拼进数据库查询容易注入，SQLite 的 Python 接口应该怎么安全传参？'),
    ('concurrent.futures', ['executor-objects', 'concurrent.futures.as_completed'], 'Executor.submit 的返回值是什么？', '把任务交给线程池后，怎样在任务完成时逐个取得结果？'),
    ('asyncio-task', ['asyncio.TaskGroup', 'asyncio.wait_for'], 'asyncio.TaskGroup 在任务失败时如何处理其他任务？', '几个协程要作为一组运行，其中一个失败后希望取消其余任务，该用什么结构？'),
    ('asyncio-sync', ['asyncio.Lock', 'asyncio.Semaphore'], 'asyncio.Semaphore 如何限制并发数量？', '异步程序同时请求外部接口时，怎样限制在途请求数？'),
    ('asyncio-queue', ['asyncio.Queue', 'asyncio.Queue.join'], 'asyncio.Queue 的 task_done 与 join 如何配合？', '协程生产者把工作交给消费者后，怎样等待所有排队任务都处理完？'),
    ('threading', ['threading.Event', 'threading.Thread.join'], 'threading.Event 的 set 与 wait 是什么用途？', '多个线程需要等待同一个完成信号，怎样通知所有等待线程继续工作？'),
    ('queue', ['queue.Queue', 'queue.Queue.task_done'], 'queue.Queue 的 task_done 与 join 如何使用？', '在线程间传递工作项后，怎样等待消费者处理完所有任务？'),
    ('subprocess', ['subprocess.run', 'subprocess.CompletedProcess'], 'subprocess.run 的 check 和 capture_output 参数分别做什么？', '运行外部程序后怎样获得标准输出，并在退出码非零时报告失败？'),
    ('contextlib', ['contextlib.contextmanager', 'contextlib.ExitStack'], 'contextmanager 装饰器中的 yield 前后分别执行什么？', '需要动态打开多个资源并确保异常时全部关闭，应如何组织上下文管理器？'),
    ('functools', ['functools.lru_cache', 'functools.cached_property'], 'lru_cache 的 maxsize 控制什么？', '函数参数相同就重复做昂贵计算，如何缓存最近使用过的计算结果？'),
    ('itertools', ['itertools.groupby', 'itertools.islice'], 'itertools.groupby 是否要求相同键的数据相邻？', '按类别分组迭代数据时，为什么同一类别可能被拆成多组，应该怎样准备输入？'),
    ('collections', ['collections.deque', 'collections.Counter'], 'deque 的 maxlen 有什么行为？', '想维护一个固定容量的最近记录窗口，满了后自动淘汰旧数据，该选哪种容器？'),
    ('dataclasses', ['dataclasses.dataclass', 'dataclasses.field'], 'dataclasses.field 的 default_factory 有什么用途？', '数据类中的列表字段怎样让每个实例各有一份，避免共享可变默认值？'),
    ('enum', ['enum.IntEnum', 'enum.Flag'], 'IntEnum 与普通 Enum 在整数运算方面有何区别？', '状态成员需要和现有整数常量兼容时，应选择哪种枚举类型？'),
    ('datetime', ['datetime.datetime.astimezone', 'aware-and-naive-objects'], 'datetime 的 aware 对象和 naive 对象如何区分？', '要把一个带时区的时间转换为另一个时区，应使用哪个方法？'),
    ('zoneinfo', ['using-zoneinfo', 'data-sources'], 'ZoneInfo 如何使用 IANA 时区名称？', '如何让同一时区的时间随着夏令时转换而使用正确的 UTC 偏移？'),
    ('decimal', ['quick-start-tutorial', 'decimal.Decimal.quantize'], 'Decimal.quantize 的用途是什么？', '金额计算希望保留两位小数并避免二进制浮点误差，应如何处理？'),
    ('hashlib', ['usage', 'hashlib.file_digest'], 'hashlib.file_digest 如何计算文件摘要？', '要检查文件内容是否变化，怎样把整个文件交给摘要算法计算校验值？'),
    ('secrets', ['secrets.token_urlsafe', 'secrets.compare_digest'], 'secrets.token_urlsafe 如何产生适合 URL 的随机令牌？', '生成找回密码链接中的安全随机字符串，为什么应使用 secrets 而非普通随机模块？'),
    ('zipfile', ['zipfile.ZipFile.testzip', 'zipfile.ZipFile.extractall'], 'ZipFile.extractall 解压不可信压缩包有哪些注意事项？', '接收用户上传的 ZIP 后，提取所有文件前需要注意哪些安全问题？'),
    ('tomllib', ['tomllib.load', 'tomllib.loads'], 'tomllib.load 要求文件以什么模式打开？', 'Python 标准库如何把 TOML 配置读成字典，是否也支持写回文件？'),
]


def download(url):
    """只下载固定官方文档地址，保留原始页面供核对。"""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise


def selected_blocks(body):
    """保留完整段落、代码、API 条目；将过大的章节展开，避免半句截断。"""
    result = []
    for node in body.find_all(recursive=False):
        if node.name in ('script', 'style', 'nav'):
            continue
        if node.name in ('section', 'dl', 'div') and len(node.get_text()) > 5000:
            result.extend(selected_blocks(node))
        else:
            result.append(node)
    return result


def fetch(spec, output):
    """选取有标题及上下文的实际章节，不生成或改写正文。"""
    slug, anchors, first, second = spec
    url = BASE + 'library/' + slug + '.html'
    raw = download(url)
    (output / '_sources' / (slug + '.html')).write_bytes(raw)
    soup = BeautifulSoup(raw, 'html.parser')
    body = soup.select_one('div.body')
    if body is None:
        raise ValueError('未找到官方正文：' + slug)
    for node in body.select('.headerlink, .viewcode-link'):
        node.decompose()
    title = body.find('h1').get_text(' ', strip=True)
    required = []
    for anchor in anchors:
        node = body.find(id=anchor)
        if node is None:
            raise ValueError('缺少章节：' + slug + '#' + anchor)
        if node.name == 'dt':
            node = node.find_parent('dl')
        required.append(node)
    pieces, size = [], 0
    for node in selected_blocks(body):
        rendered = markdownify(str(node), heading_style='ATX', code_language='python').strip()
        if not rendered:
            continue
        # 高价值 API/章节完整保留，再补充前文；过长文档明确标注为节选。
        must = any(node is wanted or wanted in node.descendants for wanted in required)
        if size + len(rendered) <= 10000 or must:
            pieces.append(rendered)
            size += len(rendered)
    for node in required:
        rendered = markdownify(str(node), heading_style='ATX', code_language='python').strip()
        if not any(rendered in piece for piece in pieces):
            pieces.append(rendered)
    content = '\n\n'.join(pieces)
    if len(content) < 1500:
        raise ValueError('章节内容过短：' + slug)
    doc = {'id': 'python-' + slug, 'title': title, 'content': '# ' + title + '\n\n' + content,
        'source_url': url, 'source_anchors': anchors, 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'excerpt': True, 'license': 'PSF License Version 2', 'characters': len(content)}
    questions = [{'id': doc['id'] + '-' + group, 'group': group, 'question': question,
                  'relevant_document_ids': [doc['id']]} for group, question in [('exact', first), ('paraphrase', second)]]
    print(slug + ': ' + str(len(content)) + ' 字符', flush=True)
    return doc, questions


def wrapped(text, width, size):
    current = ''
    for char in text:
        if pdfmetrics.stringWidth(current + char, 'WebChinese', size) > width:
            yield current
            current = ''
        current += char
    yield current


def make_pdf(doc, target):
    """真实文本排成多页 PDF，保留标题、代码、出处和许可。"""
    style = ParagraphStyle('body', fontName='WebChinese', fontSize=10, leading=16,
        wordWrap='CJK', spaceAfter=8)
    heading = ParagraphStyle('heading', parent=style, fontSize=14, leading=22, spaceBefore=12)
    title = ParagraphStyle('title', parent=heading, fontSize=19, leading=28)
    code = ParagraphStyle('code', parent=style, fontSize=8, leading=11, backColor='#f0f3f6', borderPadding=5)
    story = [Paragraph(html.escape(doc['title']), title),
             Paragraph('Python 3.14 官方中文文档章节节选 / PSF License Version 2', style),
             Paragraph(html.escape(doc['source_url']), style)]
    is_code = False
    for chunk in re.split(r'(^```[^\n]*\n)', doc['content'], flags=re.M):
        if chunk.startswith('```'):
            is_code = not is_code
            continue
        if is_code:
            for line in chunk.splitlines():
                story.append(Preformatted('\n'.join(wrapped(line, 475, 8)), code))
        else:
            for paragraph in chunk.split('\n\n'):
                if not paragraph.strip():
                    continue
                selected = heading if paragraph.startswith('#') else style
                story.append(Paragraph(html.escape(paragraph.lstrip('# ')).replace('\n', '<br/>'), selected))
    def footer(pdf, document):
        pdf.setFont('WebChinese', 8)
        pdf.drawString(45, 26, 'Python 官方文档节选 / ' + doc['id'])
        pdf.drawRightString(550, 26, str(document.page))
    SimpleDocTemplate(str(target), pagesize=(595, 842), leftMargin=45, rightMargin=45,
        topMargin=42, bottomMargin=45, title=doc['title']).build(story, onFirstPage=footer, onLaterPages=footer)


def generate(output, font):
    """下载 30 个主题，生成 15 MD、12 文字 PDF、3 扫描 PDF。"""
    output.mkdir(parents=True, exist_ok=True)
    (output / '_sources').mkdir(exist_ok=True)
    (output / 'previews').mkdir(exist_ok=True)
    pdfmetrics.registerFont(TTFont('WebChinese', str(font)))
    license_raw = download(BASE + 'license.html')
    (output / '_sources/LICENSE.html').write_bytes(license_raw)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        fetched = list(executor.map(lambda spec: fetch(spec, output), SPECS))
    docs, questions = [], []
    for index, (doc, queries) in enumerate(fetched):
        variant = 'md' if index < 15 else 'pdf_text' if index < 27 else 'pdf_scan'
        target = output / (doc['id'] + ('.md' if variant == 'md' else '.pdf'))
        if variant == 'md':
            target.write_text(doc['content'] + '\n\n---\n来源：' + doc['source_url'] + '\n许可：PSF License Version 2\n', encoding='utf-8')
        else:
            native = output / '_sources' / (doc['id'] + '.pdf') if variant == 'pdf_scan' else target
            make_pdf(doc, native)
            if variant == 'pdf_scan':
                prefix = output / 'previews' / doc['id']
                subprocess.run(['pdftoppm', '-r', '140', '-png', str(native), str(prefix)], check=True, capture_output=True)
                images = sorted(prefix.parent.glob(prefix.name + '-*.png'))
                if not images or len(images) > 20:
                    raise ValueError('扫描文档页数不在 1 到 20 范围：' + doc['id'])
                pdf = canvas.Canvas(str(target), pagesize=(595, 842), invariant=1)
                for image in images:
                    pdf.drawImage(ImageReader(str(image)), 0, 0, width=595, height=842)
                    pdf.showPage()
                pdf.save()
        doc.update(variant=variant, file_type='md' if variant == 'md' else 'pdf',
                   filename=target.name, file_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                   expected_fragments=[])
        docs.append(doc)
        questions.extend(queries)
    pairs = [('json', 'csv', '结构化数据要分别保存成 JSON 和带表头的 CSV，两种文件分别如何读写？'),
        ('pathlib', 'shutil', '如何先以面向对象的路径接口读取文本，再复制整个目录并排除临时文件？'),
        ('asyncio-task', 'asyncio-sync', '异步任务需要成组执行并且限制同时访问接口的数量，可以组合哪些机制？'),
        ('threading', 'queue', '线程生产者和消费者如何传递工作项，并使用完成信号协调退出？'),
        ('asyncio-queue', 'queue', '协程队列和线程队列分别如何等待所有已提交工作处理完？'),
        ('datetime', 'zoneinfo', '如何给时间对象附加 IANA 时区并转换到另一个时区？'),
        ('secrets', 'hashlib', '找回密码链接需要安全随机令牌，文件完整性检查需要摘要，这两种需求应分别用什么模块？'),
        ('contextlib', 'tempfile', '处理临时目录并动态打开多个资源，如何确保异常后都能清理？'),
        ('logging', 'logging.handlers', '程序如何配置基础日志，并按文件大小轮转保留历史日志？'),
        ('dataclasses', 'enum', '数据类的可变默认字段怎样初始化，字段中需要和整数兼容的状态类型又该如何定义？')]
    for index, (one, two, question) in enumerate(pairs):
        questions.append({'id': 'web-compare-' + str(index), 'group': 'multi_document', 'question': question,
                          'relevant_document_ids': ['python-' + one, 'python-' + two]})
    manifest = {'version': 3, 'synthetic': False, 'origin': 'official-python-docs', 'file_set': 'web-python-3.14-v1',
        'downloaded_at': datetime.now(timezone.utc).isoformat(), 'documents': docs, 'queries': questions}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('完成：30 篇真实章节、70 个查询，' + str(sum(d['characters'] for d in docs)) + ' 字符。', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    generate(args.output.resolve(), args.font)
