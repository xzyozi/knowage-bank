import re
from typing import Dict, Any, Tuple, List, Optional

class FlexibleMarkdownParser:
    """
    任意の Markdown テキストを解析し、YAML Frontmatter メタデータと
    site.css に適合する HTML コンポーネント群へ柔軟に変換するパーサー
    """
    def __init__(self, markdown_text: str):
        self.raw_text = markdown_text.strip() if markdown_text else ""
        self.metadata, self.body_text = self._extract_frontmatter(self.raw_text)

    def _extract_frontmatter(self, text: str) -> Tuple[Dict[str, Any], str]:
        """YAML Frontmatter (--- ... ---) を抽出・パース"""
        metadata: Dict[str, Any] = {}
        body = text
        
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                yaml_str = parts[1].strip()
                body = parts[2].strip()
                for line in yaml_str.splitlines():
                    line = line.strip()
                    if ":" in line and not line.startswith("#"):
                        key, val = line.split(":", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if val.startswith("[") and val.endswith("]"):
                            items = [i.strip().strip('"').strip("'") for i in val[1:-1].split(",") if i.strip()]
                            metadata[key] = items
                        else:
                            metadata[key] = val

        # 本文冒頭の # 見出し（H1）の処理・クレンジング
        h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if h1_match:
            if "title" not in metadata or not metadata["title"]:
                metadata["title"] = h1_match.group(1).strip()
            # 本文冒頭付近の第1位の # 見出し行をクレンジング除去（タイトルとの二重化防止）
            body = re.sub(r"^#\s+.+$\n?", "", body, count=1, flags=re.MULTILINE).strip()

        return metadata, body

    def _extract_key_points(self, text: str) -> Tuple[List[str], str]:
        """## 要点 / まとめ セクションを検出・抽出し、key_points リストを返却"""
        key_points = []
        kp_pattern = r"^##\s*(?:要点|まとめ|Key Points)\s*$\n((?:[-*+]\s+.*\n?)+)"
        kp_match = re.search(kp_pattern, text, re.MULTILINE | re.IGNORECASE)
        
        clean_text = text
        if kp_match:
            lines = kp_match.group(1).strip().splitlines()
            for line in lines:
                line_str = re.sub(r"^[-*+]\s+", "", line.strip())
                if line_str:
                    key_points.append(line_str)
            clean_text = re.sub(kp_pattern, "", text, flags=re.MULTILINE | re.IGNORECASE).strip()
            
        return key_points, clean_text

    def _extract_lead(self, text: str) -> Tuple[str, str]:
        """本文先頭の最初の段落をリード文 (lead) として抽出"""
        lines = text.strip().splitlines()
        lead_lines = []
        body_lines = []
        in_lead = True
        
        for line in lines:
            stripped = line.strip()
            if in_lead:
                if stripped.startswith("#") or stripped.startswith("- ") or stripped.startswith("* ") or re.match(r"^\d+\.", stripped):
                    in_lead = False
                    body_lines.append(line)
                elif not stripped:
                    if lead_lines:
                        in_lead = False
                else:
                    lead_lines.append(stripped)
            else:
                body_lines.append(line)
                
        lead_text = " ".join(lead_lines)
        return lead_text, "\n".join(body_lines).strip()

    def _extract_qa_blocks(self, text: str) -> Tuple[List[Dict[str, str]], str]:
        """Q&A 形式のブロックを検出・抽出、および本文からの除去"""
        qa_list = []
        qa_pattern = r"(?:Q|質問)[:：]\s*(.*?)\n+(?:A|回答)[:：]\s*(.*?)(?=\n\n|\n#|\Z)"
        qa_matches = list(re.finditer(qa_pattern, text, re.DOTALL | re.IGNORECASE))
        
        for m in qa_matches:
            q = m.group(1).strip().replace("\n", " ")
            a = m.group(2).strip().replace("\n", " ")
            qa_list.append({"q": q, "a": a})
        
        # 本文からの除去
        clean_text = re.sub(qa_pattern, "", text, flags=re.DOTALL | re.IGNORECASE).strip()
        
        return qa_list, clean_text

    def _extract_references(self, text: str) -> List[Dict[str, str]]:
        """参考資料・リンクブロックの抽出"""
        refs = []
        # [タイトル](URL) または - URL パターン
        link_matches = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text)
        seen_urls = set()
        for title, url in link_matches:
            if url not in seen_urls:
                seen_urls.add(url)
                refs.append({"title": title.strip(), "url": url.strip()})
        return refs

    def convert_markdown_to_html(self, md_text: Optional[str] = None) -> str:
        """
        Markdown テキストを site.css に対応した HTML 要素へ変換
        """
        text = md_text if md_text is not None else self.body_text
        if not text:
            return ""

        lines = text.splitlines()
        html_lines = []
        in_code_block = False
        code_lang = ""
        code_lines = []
        in_ul = False
        in_ol = False
        in_table = False
        table_rows = []

        def close_lists_and_table():
            nonlocal in_ul, in_ol, in_table, table_rows
            res = []
            if in_ul:
                res.append("</ul>")
                in_ul = False
            if in_ol:
                res.append("</ol>")
                in_ol = False
            if in_table and table_rows:
                res.append(self._render_table_html(table_rows))
                in_table = False
                table_rows = []
            return res

        for line in lines:
            stripped = line.strip()

            # コードブロック処理
            if stripped.startswith("```"):
                if in_code_block:
                    # コードブロック終了
                    code_content = "\n".join(code_lines)
                    if code_lang == "mermaid":
                        html_lines.append(f'<div class="mermaid">\n{code_content}\n</div>')
                    else:
                        code_content = code_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        lang_class = f' class="language-{code_lang}"' if code_lang else ""
                        html_lines.append(f'<pre><code{lang_class}>{code_content}</code></pre>')
                    in_code_block = False
                    code_lines = []
                else:
                    html_lines.extend(close_lists_and_table())
                    in_code_block = True
                    code_lang = stripped[3:].strip()
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # テーブル (Pipe Table) の判定
            if stripped.startswith("|") and stripped.endswith("|"):
                if not in_table:
                    html_lines.extend(close_lists_and_table())
                    in_table = True
                table_rows.append(stripped)
                continue
            elif in_table:
                html_lines.extend(close_lists_and_table())

            # 空行
            if not stripped:
                html_lines.extend(close_lists_and_table())
                continue

            # 見出し H1 / H2
            if stripped.startswith("# ") or stripped.startswith("## "):
                html_lines.extend(close_lists_and_table())
                prefix_len = 2 if stripped.startswith("# ") else 3
                h2_text = self._inline_markdown_to_html(stripped[prefix_len:].strip())
                html_lines.append(f"<h2>{h2_text}</h2>")
                continue

            # 見出し H3
            if stripped.startswith("### "):
                html_lines.extend(close_lists_and_table())
                h3_text = self._inline_markdown_to_html(stripped[4:].strip())
                html_lines.append(f"<h3>{h3_text}</h3>")
                continue

            # 箇条書き (ul)
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_ul:
                    html_lines.extend(close_lists_and_table())
                    html_lines.append("<ul>")
                    in_ul = True
                li_text = self._inline_markdown_to_html(stripped[2:].strip())
                html_lines.append(f"<li>{li_text}</li>")
                continue

            # 番号付きリスト (ol)
            ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
            if ol_match:
                if not in_ol:
                    html_lines.extend(close_lists_and_table())
                    html_lines.append("<ol>")
                    in_ol = True
                li_text = self._inline_markdown_to_html(ol_match.group(1).strip())
                html_lines.append(f"<li>{li_text}</li>")
                continue

            # リスト終了後の通常の段落
            html_lines.extend(close_lists_and_table())
            p_text = self._inline_markdown_to_html(stripped)
            html_lines.append(f"<p>{p_text}</p>")

        html_lines.extend(close_lists_and_table())
        return "\n".join(html_lines)

    def _render_table_html(self, rows: List[str]) -> str:
        """Markdown Pipe Table 行を site.css 適合の <table class="figure"> へレンダリング"""
        if not rows:
            return ""

        table_html = ['<table class="figure">']
        
        def parse_row_cells(row_str: str) -> List[str]:
            cells = [c.strip() for c in row_str.strip("|").split("|")]
            return cells

        # ヘッダー行
        header_cells = parse_row_cells(rows[0])
        table_html.append("  <thead>")
        table_html.append("    <tr>")
        for cell in header_cells:
            cell_html = self._inline_markdown_to_html(cell)
            table_html.append(f'      <th scope="col">{cell_html}</th>')
        table_html.append("    </tr>")
        table_html.append("  </thead>")

        # データ行
        table_html.append("  <tbody>")
        for row in rows[1:]:
            # 区切り行 | :--- | :--- | のスキップ
            if re.match(r"^\s*\|?\s*:?-+:?\s*\|", row):
                continue
            cells = parse_row_cells(row)
            table_html.append("    <tr>")
            for cell in cells:
                cell_html = self._inline_markdown_to_html(cell)
                table_html.append(f"      <td>{cell_html}</td>")
            table_html.append("    </tr>")
        table_html.append("  </tbody>")
        table_html.append("</table>")

        return "\n".join(table_html)

    def _inline_markdown_to_html(self, text: str) -> str:
        """インラインの Markdown (強調、リンク、コード) を HTML 化"""
        # 太字 **text**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # リンク [text](url)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', text)
        # インラインコード `code`
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    def parse(self) -> Dict[str, Any]:
        """パース完了オブジェクトを返却"""
        qa, body_after_qa = self._extract_qa_blocks(self.body_text)
        key_points, body_after_kp = self._extract_key_points(body_after_qa)
        
        # lead が Frontmatter にない場合、本文先頭段落から自動抽出
        lead = self.metadata.get("lead", "")
        if not lead:
            extracted_lead, remaining_body = self._extract_lead(body_after_kp)
            lead = extracted_lead
            body_final = remaining_body
        else:
            body_final = body_after_kp

        refs = self._extract_references(body_final)
        body_html = self.convert_markdown_to_html(body_final)

        return {
            "title": self.metadata.get("title", "無題の記事"),
            "eyebrow": self.metadata.get("eyebrow", "技術ノート"),
            "lead": lead,
            "tags": self.metadata.get("tags", []),
            "created_at": self.metadata.get("created_at"),
            "qa": qa,
            "key_points": key_points,
            "references": refs,
            "body_html": body_html,
            "raw_metadata": self.metadata,
        }
