"""纪要结构转换保留格式、列表层级和表格。"""
from app.modules.meetings.rich_text import state_from_minutes, minutes_from_state


def test_markdown_roundtrip_preserves_heading_marks_nested_list_and_table():
    value = '# 讨论\n\n## 行动项\n\n- **确认方案**\n  - 责任人：[同事](https://example.com)\n\n|事项|状态|\n|---|---|\n|联调|待确认|'
    content, blocks = minutes_from_state(state_from_minutes(value))
    assert '# 讨论' in content and '## 行动项' in content and '**确认方案**' in content
    assert blocks[2]['children'][0]['type'] == 'bulletListItem'
    assert '[同事](https://example.com)' in content
    assert blocks[3]['type'] == 'table'
    assert '| 联调 | 待确认 |' in content
    next_content, next_blocks = minutes_from_state(state_from_minutes(content, blocks))
    assert next_content == content and next_blocks == blocks
