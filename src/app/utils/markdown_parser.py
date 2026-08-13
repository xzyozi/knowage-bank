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

        # タイトルが本文の1行目 # 見出しにある場合のフォールバック
        if "title" not in metadata or not metadata["title"]:
            title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if title_match:
                metadata["title"] = title_match.group(1).strip()
                body = re.sub(r"^#\s+.+$\n?", "", body, count=1, flags=re.MULTILINE).strip()

        return metadata, body

    def _extract_qa_blocks(self, text: str) -> List[Dict[str, str]]:
        """Q&A 形式のブロックを検出・抽出"""
        qa_list = []
        # Q: ... A: ... パターンまたは Q&A 見出し下の項目
        qa_matches = re.findall(r"(?:Q|質問)[:：]\s*(.*?)\n+(?:A|回答)[:：]\s*(.*?)(?=\n(?:Q|質問)[:：]|\n##|\Z)", text, re.DOTALL | re.IGNORECASE)
        for q, a in qa_matches:
            qa_list.append({
                "q": q.strip().replace("\n", " "),
                "a": a.strip().replace("\n", " ")
            })
        return qa_list

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

        def close_lists():
            nonlocal in_ul, in_ol
            res = []
            if in_ul:
                res.append("</ul>")
                in_ul = False
            if in_ol:
                res.append("</ol>")
                in_ol = False
            return res

        for line in lines:
            stripped = line.strip()

            # コードブロック処理
            if stripped.startswith("```"):
                if in_code_block:
                    # コードブロック終了
                    code_content = "\n".join(code_lines)
                    # HTML エスケープ
                    code_content = code_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    lang_class = f' class="language-{code_lang}"' if code_lang else ""
                    html_lines.append(f'<pre><code{lang_class}>{code_content}</code></pre>')
                    in_code_block = False
                    code_lines = []
                else:
                    html_lines.extend(close_lists())
                    in_code_block = True
                    code_lang = stripped[3:].strip()
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # 空行
            if not stripped:
                html_lines.extend(close_lists())
                continue

            # 見出し H2
            if stripped.startswith("## "):
                html_lines.extend(close_lists())
                h2_text = self._inline_markdown_to_html(stripped[3:].strip())
                html_lines.append(f"<h2>{h2_text}</h2>")
                continue

            # 見出し H3
            if stripped.startswith("### "):
                html_lines.extend(close_lists())
                h3_text = self._inline_markdown_to_html(stripped[4:].strip())
                html_lines.append(f"<h3>{h3_text}</h3>")
                continue

            # 箇条書き (ul)
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_ul:
                    html_lines.extend(close_lists())
                    html_lines.append("<ul>")
                    in_ul = True
                li_text = self._inline_markdown_to_html(stripped[2:].strip())
                html_lines.append(f"<li>{li_text}</li>")
                continue

            # 番号付きリスト (ol)
            ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
            if ol_match:
                if not in_ol:
                    html_lines.extend(close_lists())
                    html_lines.append("<ol>")
                    in_ol = True
                li_text = self._inline_markdown_to_html(ol_match.group(1).strip())
                html_lines.append(f"<li>{li_text}</li>")
                continue

            # リスト終了後の通常の段落
            html_lines.extend(close_lists())
            p_text = self._inline_markdown_to_html(stripped)
            html_lines.append(f"<p>{p_text}</p>")

        html_lines.extend(close_lists())
        return "\n".join(html_lines)

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
        qa = self._extract_qa_blocks(self.body_text)
        refs = self._extract_references(self.body_text)
        body_html = self.convert_markdown_to_html(self.body_text)

        return {
            "title": self.metadata.get("title", "無題の記事"),
            "eyebrow": self.metadata.get("eyebrow", "技術ノート"),
            "tags": self.metadata.get("tags", []),
            "created_at": self.metadata.get("created_at"),
            "qa": qa,
            "references": refs,
            "body_html": body_html,
            "raw_metadata": self.metadata,
        }
