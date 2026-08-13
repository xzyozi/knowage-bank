import os
import json
from datetime import datetime
from jinja2 import Template
from app.utils.logger import logger
from app.utils.markdown_parser import FlexibleMarkdownParser

class ArticleBuilder:
    def __init__(self) -> None:
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "category_config.json")
        self.template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "article_template.html")
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
        """JSONデータまたは任意のMarkdownデータからHTML文字列を生成する"""
        t = Template(self.template_content)
        
        # 自由形式の Markdown テキストが直接渡された場合
        markdown_text = data.get("markdown_text") or data.get("markdown")
        parsed_data = {}
        if markdown_text:
            parser = FlexibleMarkdownParser(markdown_text)
            parsed_data = parser.parse()

        # メタデータ・項目の統合
        raw_eyebrow = data.get("eyebrow") or parsed_data.get("eyebrow", "未分類")
        normalized_eyebrow = self.normalize_eyebrow(raw_eyebrow)
        
        now = datetime.now()
        
        render_data = {
            "title": data.get("title") or parsed_data.get("title", "無題の記事"),
            "eyebrow": normalized_eyebrow,
            "lead": data.get("lead", ""),
            "date_str": now.strftime("%Y-%m-%d"),
            "display_date": f"{now.year}年{now.month}月{now.day}日",
            "qa": data.get("qa") or parsed_data.get("qa", []),
            "sections": data.get("sections", []),
            "body_html": data.get("body_html") or parsed_data.get("body_html", ""),
            "key_points": data.get("key_points") or parsed_data.get("key_points", []),
            "references": data.get("references") or parsed_data.get("references", [])
        }
        
        return t.render(render_data)

    def save_article(self, data: dict, filename: str) -> str:
        """HTML記事をビルドして保存する"""
        html_str = self.build_article_html(data)
        
        articles_dir = os.path.join("public", "articles")
        os.makedirs(articles_dir, exist_ok=True)
        
        output_path = os.path.join(articles_dir, filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_str)
            
        logger.info(f"Article saved and built successfully: {output_path}")
        return output_path
