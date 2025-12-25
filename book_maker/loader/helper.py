import re
import backoff
import logging
from copy import copy

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class EPUBBookLoaderHelper:
    def __init__(
        self, translate_model, accumulated_num, translation_style, context_flag
    ):
        self.translate_model = translate_model
        self.accumulated_num = accumulated_num
        self.translation_style = translation_style
        self.context_flag = context_flag

    def insert_trans(self, p, text, translation_style="", single_translate=False):
        if text is None:
            text = ""
        if (
            p.string is not None
            and p.string.replace(" ", "").strip() == text.replace(" ", "").strip()
        ):
            return

        from bs4 import NavigableString, BeautifulSoup as bs, Tag
        
        if hasattr(p, "get") and p.get("class"):
            for cls in p.get("class"):
                if cls.startswith("toc-heading-"):
                    from bs4 import BeautifulSoup as bs
                    clean_text = bs(text, "html.parser").get_text() if text else ""
                    a_tag = p.find("a")
                    if a_tag:
                        a_tag.string = f"{a_tag.text}({clean_text})"
                    else:
                        p.string = f"{p.text}({clean_text})"
                    return

        # Helper to safely copy a node to avoid parentage issues
        def safe_copy_node(node):
            if isinstance(node, Tag):
                return copy(node)
            return NavigableString(str(node))

        if isinstance(p, NavigableString):
            if "<" in text and ">" in text:
                temp_soup = bs(f"<body>{text}</body>", "html.parser")
                body = temp_soup.find("body") or temp_soup
                current = p
                for child in list(body.contents):
                    new_node = safe_copy_node(child)
                    current.insert_after(new_node)
                    current = new_node
            else:
                new_p = NavigableString(text)
                p.insert_after(new_p)
            
            if single_translate:
                p.extract()
            return

        # For Tag elements (p, div, etc.), we construct a full HTML string and parse it.
        # This is the most robust way to ensure all nodes are correctly interleaved and adopted.
        if "<" in text and ">" in text:
            attrs_str = ""
            for k, v in p.attrs.items():
                val = " ".join(v) if isinstance(v, list) else str(v)
                # Escape double quotes in attribute values
                val = val.replace('"', '&quot;')
                attrs_str += f' {k}="{val}"'
            
            html = f"<{p.name}{attrs_str}>{text}</{p.name}>"
            fragment_soup = bs(html, "html.parser")
            new_p = fragment_soup.find(p.name)
            if not new_p:
                # Fallback if find fails
                new_p = copy(p)
                new_p.string = text
        else:
            new_p = copy(p)
            new_p.string = text
            
        if translation_style != "":
            new_p["style"] = translation_style
        
        # Add classes
        # For new_p (translation)
        existing_class = new_p.get("class", [])
        if isinstance(existing_class, str):
            existing_class = [existing_class]
        # Ensure it's a list copy to handle BS4 attribute behavior safely
        existing_class = list(existing_class)
        
        if "origin" in existing_class:
            existing_class.remove("origin")
        if "translate" not in existing_class:
            existing_class.append("translate")
        new_p["class"] = existing_class
        
        # For p (original)
        if isinstance(p, Tag):
            existing_origin_class = p.get("class", [])
            if isinstance(existing_origin_class, str):
                existing_origin_class = [existing_origin_class]
            # Ensure it's a list copy
            existing_origin_class = list(existing_origin_class)
            
            if "translate" in existing_origin_class:
                existing_origin_class.remove("translate")
            if "origin" not in existing_origin_class:
                existing_origin_class.append("origin")
            p["class"] = existing_origin_class
            
        p.insert_after(new_p)
        if single_translate:
            p.extract()

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_backoff=lambda details: logger.warning(f"retry backoff: {details}"),
        on_giveup=lambda details: logger.warning(f"retry abort: {details}"),
        jitter=None,
    )
    def translate_with_backoff(self, text, context_flag=False):
        return self.translate_model.translate(text, context_flag)

    def deal_new(self, p, wait_p_list, single_translate=False):
        self.deal_old(wait_p_list, single_translate, self.context_flag)
        p_text = p.decode_contents() if hasattr(p, "contents") and p.contents else p.text
        translation = shorter_result_link(self.translate_with_backoff(p_text, self.context_flag))
        self.insert_trans(
            p,
            translation,
            self.translation_style,
            single_translate,
        )
        return [translation]

    def deal_old(self, wait_p_list, single_translate=False, context_flag=False):
        if not wait_p_list:
            return []

        result_txt_list = self.translate_model.translate_list(wait_p_list)

        for i in range(len(wait_p_list)):
            if i < len(result_txt_list):
                p = wait_p_list[i]
                self.insert_trans(
                    p,
                    shorter_result_link(result_txt_list[i]),
                    self.translation_style,
                    single_translate,
                )

        wait_p_list.clear()
        return result_txt_list


url_pattern = r"(http[s]?://|www\.)+(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"


def is_text_link(text):
    return bool(re.compile(url_pattern).match(text.strip()))


def is_text_tail_link(text, num=80):
    text = text.strip()
    pattern = r".*" + url_pattern + r"$"
    return bool(re.compile(pattern).match(text)) and len(text) < num


def shorter_result_link(text, num=20):
    match = re.search(url_pattern, text)

    if not match or len(match.group()) < num:
        return text

    return re.compile(url_pattern).sub("...", text)


def is_text_source(text):
    return text.strip().startswith("Source: ")


def is_text_list(text, num=80):
    text = text.strip()
    return re.match(r"^Listing\s*\d+", text) and len(text) < num


def is_text_figure(text, num=80):
    text = text.strip()
    return re.match(r"^Figure\s*\d+", text) and len(text) < num


def is_text_digit_and_space(s):
    for c in s:
        if not c.isdigit() and not c.isspace():
            return False
    return True


def is_text_isbn(s):
    pattern = r"^[Ee]?ISBN\s*\d[\d\s]*$"
    return bool(re.match(pattern, s))


def not_trans(s):
    return any(
        [
            is_text_link(s),
            is_text_tail_link(s),
            is_text_source(s),
            is_text_list(s),
            is_text_figure(s),
            is_text_digit_and_space(s),
            is_text_isbn(s),
        ]
    )
