import re
from typing import Any, Dict, List, Tuple


def extract_citation_order(body_html: str) -> List[int]:
    """本文中の [N] または [N, M] の出現順に旧番号リストを抽出"""
    matches = re.findall(r"\[(\d+(?:,\s*\d+)*)\]", body_html)
    order = []
    for match in matches:
        nums = [int(n.strip()) for n in match.split(",") if n.strip().isdigit()]
        for n in nums:
            if n not in order:
                order.append(n)
    return order


def apply_citations(
    body_html: str,
    raw_refs: Dict[int, Dict[str, str]],
    citations_keep: List[int],
    citation_labels: Dict[Any, str],
    lead_text: str = "",
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Stage 3: 本文およびリード文中の引用番号をリナンバリング (1, 2, 3...) して <sup><a href="#ref-N">N</a></sup> に置換し、
    新番号順の参考文献リスト (ref_list) を生成する。
    """
    if not raw_refs:
        return body_html, lead_text, []

    # 1. 本文およびリード文中の出現順で新番号を確定（1, 2, 3...）
    combined_text = lead_text + "\n" + body_html
    appearance_order = extract_citation_order(combined_text)

    # citations_keep が指定されている場合はフィルタリング。無指定の場合は出現順全てを対象
    if citations_keep:
        kept_in_order = [n for n in appearance_order if n in citations_keep]
    else:
        kept_in_order = [n for n in appearance_order if n in raw_refs]

    # 新番号マッピング old_to_new (1-indexed)
    old_to_new: Dict[int, int] = {}
    new_counter = 1
    for old in kept_in_order:
        if old not in old_to_new and old in raw_refs:
            old_to_new[old] = new_counter
            new_counter += 1

    # 2. [11, 20] パターンを <sup><a href="#ref-N">N</a></sup> に置換
    def replace_bracket(match: re.Match[str]) -> str:
        nums = [int(n.strip()) for n in match.group(1).split(",") if n.strip().isdigit()]
        kept = [old_to_new[n] for n in nums if n in old_to_new]
        if not kept:
            return ""  # 全て除外なら削除
        links = ",".join(f'<a href="#ref-{n}">{n}</a>' for n in kept)
        return f"<sup>{links}</sup>"

    transformed_html = re.sub(r"\[(\d+(?:,\s*\d+)*)\]", replace_bracket, body_html)
    transformed_lead = re.sub(r"\[(\d+(?:,\s*\d+)*)\]", replace_bracket, lead_text)

    # 3. 参考文献リスト構築（新番号順）
    ref_list = []
    for old, new in sorted(old_to_new.items(), key=lambda x: x[1]):
        label = citation_labels.get(str(old)) or citation_labels.get(old) or raw_refs[old]["title"]
        ref_list.append({"n": new, "label": label, "url": raw_refs[old]["url"]})

    return transformed_html, transformed_lead, ref_list
