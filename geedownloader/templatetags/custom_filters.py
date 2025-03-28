from django import template
from datetime import datetime

register = template.Library()


@register.filter
def timestamp_to_date(timestamp):
    """Convert a millisecond timestamp to a formatted date string"""
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return timestamp  # 返回原始值如果转换失败
