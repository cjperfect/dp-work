"""生成混合检索语料；开发工具依赖 reportlab、Poppler，不进入生产 Sidecar。"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from .retrieval_corpus import build_corpus


def lines(text, width=490, size=13):
    """按字体实际宽度换行，中英文均不裁切。"""
    current = ''
    for char in text:
        if pdfmetrics.stringWidth(current + char, 'EvalChinese', size) > width:
            yield current
            current = ''
        current += char
    if current:
        yield current


def draw_text(pdf, text, y, size=13, x=52, width=490):
    """绘制一个段落并返回下一行纵坐标。"""
    pdf.setFont('EvalChinese', size)
    pdf.setFillColorRGB(.12, .16, .2)
    for line in lines(text, width, size):
        pdf.drawString(x, y, line)
        y -= size * 1.7
    return y - 10


def create_pdf(doc, target, flow=False):
    """生成可读原页；流程图事实只出现在图中，不附隐形参考答案。"""
    pdf = canvas.Canvas(str(target), pagesize=(595, 842), invariant=1)
    pdf.setTitle(doc['title'])
    pdf.setFillColorRGB(.15, .35, .6)
    pdf.rect(0, 806, 595, 36, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont('EvalChinese', 10)
    pdf.drawString(52, 819, 'DP WORK / SYNTHETIC RETRIEVAL EVALUATION')
    y = draw_text(pdf, doc['title'], 764, size=20)
    paragraphs = doc['content'].split('\n\n')[1:]
    if flow:
        y = draw_text(pdf, paragraphs[0], y, size=12)
        fact = paragraphs[2]
        cleaning = re.search('清洁方式：(.*?)。', fact).group(1)
        fault = re.search('若出现“(.*?)”', fact).group(1)
        nodes = [('清洁与检查', cleaning), ('异常现象', fault),
                 ('立即处置', '立即停机并断开电源'), ('后续处理', '联系售后，不得自行拆机')]
        for index, (title, body) in enumerate(nodes):
            bottom = y - 76
            pdf.setStrokeColorRGB(.3, .5, .7)
            pdf.setFillColorRGB(.94, .97, 1)
            pdf.roundRect(76, bottom, 443, 72, 9, fill=1, stroke=1)
            draw_text(pdf, title, y - 24, size=14, x=94, width=405)
            draw_text(pdf, body, y - 49, size=12, x=94, width=405)
            if index < len(nodes) - 1:
                pdf.line(297, bottom, 297, bottom - 20)
                pdf.line(297, bottom - 20, 292, bottom - 14)
                pdf.line(297, bottom - 20, 302, bottom - 14)
            y -= 102
    else:
        for paragraph in paragraphs:
            y = draw_text(pdf, paragraph.lstrip('# '), y, size=13)
    if y < 60:
        raise ValueError('测试页内容溢出，需要重新排版。')
    draw_text(pdf, '合成测试资料 / 非真实产品参数 / 第 1 页', 35, size=9)
    pdf.save()


def generate(output, font):
    """生成 10 MD、10 文字 PDF、5 扫描 PDF 和 5 流程图扫描 PDF。"""
    pdfmetrics.registerFont(TTFont('EvalChinese', str(font)))
    output.mkdir(parents=True, exist_ok=True)
    previews = output / 'previews'
    previews.mkdir(exist_ok=True)
    corpus = build_corpus()
    for doc in corpus['documents']:
        kind = doc['id'].rsplit('-', 1)[1]
        product_index = corpus['documents'].index(doc) // 3
        variant = 'md' if kind == 'warranty' else 'pdf_text' if kind == 'spec' else 'pdf_scan' if product_index % 2 == 0 else 'pdf_flow'
        doc['variant'] = variant
        doc['file_type'] = 'md' if variant == 'md' else 'pdf'
        target = output / (doc['id'] + '.' + doc['file_type'])
        if variant == 'md':
            target.write_text(doc['content'], encoding='utf-8')
        else:
            original = previews / (doc['id'] + '-native.pdf') if variant != 'pdf_text' else target
            create_pdf(doc, original, flow=variant == 'pdf_flow')
            preview = previews / doc['id']
            subprocess.run(['pdftoppm', '-r', '150', '-singlefile', '-png', str(original), str(preview)], check=True, capture_output=True)
            if variant != 'pdf_text':
                pdf = canvas.Canvas(str(target), pagesize=(595, 842), invariant=1)
                pdf.drawImage(ImageReader(str(preview) + '.png'), 0, 0, width=595, height=842)
                pdf.save()
        doc['filename'] = target.name
        doc['file_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        fact = doc['content'].split('\n\n')[3]
        if kind == 'spec':
            doc['expected_fragments'] = re.findall(r'\d+(?:mAh| 分钟)', fact)
        elif kind == 'care':
            doc['expected_fragments'] = [re.search('清洁方式：(.*?)。', fact).group(1),
                re.search('若出现“(.*?)”', fact).group(1), '停机', '断开电源', '联系售后', '不得自行拆机']
        else:
            doc['expected_fragments'] = ['序列号', '购买凭证', '故障视频']
    corpus.update(version=2, file_set='mixed-pdf-md-v1')
    (output / 'manifest.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding='utf-8')
    print('已生成 30 篇混合文档及预览，清单：' + str(output / 'manifest.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    generate(args.output.resolve(), args.font)
