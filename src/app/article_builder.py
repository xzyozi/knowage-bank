from datetime import datetime
import json
import os

from jinja2 import Template

from app.utils.atomic_file import atomic_write_text
from app.utils.citation_processor import apply_citations
from app.utils.logger import logger
from app.utils.markdown_cleaner import parse_reference_footer
from app.utils.markdown_parser import FlexibleMarkdownParser


class ArticleBuilder:
    def __init__(self) -> None:
        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "category_config.json"
        )
        self.template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates", "article_template.html"
        )
        self.clusters = self._load_category_config()
        self.template_content = self._load_template()

    def _load_category_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("clusters", {})
        except Exception as e:
            logger.error(f"Failed to load category config: {e}")
            return {}

    def _load_template(self) -> str:
        try:
            with open(self.template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load template file: {e}")
            return ""

    def normalize_eyebrow(self, input_eyebrow: str) -> str:
        """入力されたカテゴリ表記を category_config.json 内の正式名に揺らぎ吸収マッピングする"""
        if not input_eyebrow:
            return "未分類"

        # 完全一致チェック
        for cl_info in self.clusters.values():
            if cl_info.get("eyebrow") == input_eyebrow:
                return input_eyebrow

        # 部分一致 / ゆらぎ吸収チェック
        cleaned_input = input_eyebrow.replace(" ", "").lower()
        for cl_info in self.clusters.values():
            target = cl_info.get("eyebrow", "")
            cleaned_target = target.replace(" ", "").lower()
            if cleaned_input in cleaned_target or cleaned_target in cleaned_input:
                logger.info(f"Normalized eyebrow: '{input_eyebrow}' -> '{target}'")
                return target

        logger.warning(f"Could not find matching category for eyebrow: '{input_eyebrow}'. Using raw input.")
        return input_eyebrow

    def build_article_html(self, data: dict) -> str:
        """Markdown原本からHTML文字列をパイプライン（Stage 0.5〜5）生成する。"""
        raw_markdown = data.get("markdown_text")
        if not isinstance(raw_markdown, str) or not raw_markdown.strip():
            raise ValueError("markdown_text is required to build an article.")

        # Stage 0.5: クレンジング & 参考文献フッターの分離
        clean_body_md, raw_refs = parse_reference_footer(raw_markdown)

        # Stage 3a: Markdown -> HTML 基本変換
        parsed_data = FlexibleMarkdownParser(clean_body_md).parse()
        body_html = parsed_data.get("body_html", "")

        # Stage 3b: 引用制御メタデータの適用とリナンバリング
        body_html, lead_text, ref_list = apply_citations(
            body_html,
            raw_refs,
            data.get("citations_keep", []),
            data.get("citation_labels", {}),
            parsed_data.get("lead", ""),
        )

        now = datetime.now()
        render_data = {
            "title": parsed_data.get("title", "無題の記事"),
            "eyebrow": self.normalize_eyebrow(parsed_data.get("eyebrow", "未分類")),
            "lead": lead_text or parsed_data.get("lead", ""),
            "date_str": now.strftime("%Y-%m-%d"),
            "display_date": f"{now.year}年{now.month}月{now.day}日",
            "qa": parsed_data.get("qa", []),
            "sections": [],
            "body_html": body_html,
            "key_points": parsed_data.get("key_points", []),
            "references": parsed_data.get("references", []),
            "ref_list": ref_list,
        }
        return Template(self.template_content).render(render_data)

    def save_article(self, data: dict, filename: str) -> str:
        """HTML記事をビルドして保存する"""
        html_str = self.build_article_html(data)

        articles_dir = os.path.join("public", "articles")
        output_path = os.path.join(articles_dir, filename)

        atomic_write_text(output_path, html_str)

        logger.info(f"Article saved and built successfully: {output_path}")
        return output_path
