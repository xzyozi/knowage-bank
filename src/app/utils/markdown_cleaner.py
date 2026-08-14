import re
from typing import Dict, Any, Tuple

def parse_reference_footer(md_text: str) -> Tuple[str, Dict[int, Dict[str, str]]]:
    """
    Stage 0.5: クレンジング & 参考文献フッターの分離
    末尾の [N] タイトル \n URL: https://... ブロックを解析し、
    クレンジングされた本文 (body_md) と raw_refs: dict[int, {title, url}] を分離・取得する。
    [108, 130, 164] のような複数番号1エントリにも対応。
    """
    pattern = re.compile(
        r'^\[(?P<nums>[\d,\s]+)\]\s+(?P<title>.+?)(?:\s*\(source nr:.*?\))?\s*$\n\s*URL:\s*(?P<url>\S+)',
        re.MULTILINE
    )
    
    raw_refs: Dict[int, Dict[str, str]] = {}
    
    # 全マッチの出現位置を把握し、参考文献フッターの開始位置を特定
    matches = list(pattern.finditer(md_text))
    if not matches:
        return md_text.strip(), raw_refs

    first_match_start = matches[0].start()

    for m in matches:
        nums_str = m.group('nums')
        title = m.group('title').strip()
        url = m.group('url').strip()
        
        nums = [int(n.strip()) for n in nums_str.split(',') if n.strip().isdigit()]
        for n in nums:
            raw_refs[n] = {"title": title, "url": url}

    # フッター部分を取り除いた本文
    body_md = md_text[:first_match_start].strip()
    
    # 目次セクション (TOC) や二重見出しの簡単なクレンジング
    body_md = re.sub(r'^(?:#+)?\s*(?:目次|Table of Contents)\s*$\n(?:[-*+]\s+.*\n)+', '', body_md, flags=re.MULTILINE | re.IGNORECASE)
    
    return body_md.strip(), raw_refs
