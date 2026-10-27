"""桌面 Sidecar 独立程序及隔离解析子进程入口。"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == '--parse-worker':
        content = sys.stdin.buffer.read(20 * 1024 * 1024 + 1)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                if sys.argv[2] == 'pdf':
                    from src.knowledge.parsers.pdf import parse_pdf
                    result = parse_pdf(content, Path(sys.argv[3]))
                elif sys.argv[2] == 'word':
                    from src.knowledge.parsers.word import parse_word
                    result = parse_word(content)
                else:
                    raise ValueError('不支持的解析类型。')
        except ValueError as cause:
            result = {'error': str(cause)}
        except Exception:
            result = {'error': '文档解析失败，请检查文件后重试。'}
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
        return
    if "--stdio" in sys.argv:
        from src.transport.stdio import main as stdio_main
        stdio_main()
        return
    import uvicorn
    from src.main import app
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('PORT', '8001')))


if __name__ == '__main__':
    main()
