import re
from copy import copy

class BatchStrategy:
    def translate_list(self, plist):
        plist_len = len(plist)
        
        # Create a list of original texts and add clear numbering markers to each paragraph
        formatted_text = ""
        for i, p in enumerate(plist, 1):
            temp_p = copy(p)
            for sup in temp_p.find_all("sup"):
                sup.extract()
            para_text = temp_p.decode_contents() if hasattr(temp_p, "contents") and temp_p.contents else temp_p.get_text().strip()
            # Using special delimiters and clear numbering
            formatted_text += f"PARAGRAPH {i}:\n{para_text}\n\n"

        print(f"plist len = {plist_len}")

        # Save original prompt template
        original_prompt_template = self.prompt_template if hasattr(self, "prompt_template") else self.prompt

        structured_prompt = (
            f"Translate the following {plist_len} paragraphs to {{language}}. "
            f"CRUCIAL INSTRUCTION: Format your response using EXACTLY this structure:\n\n"
            f"TRANSLATION OF PARAGRAPH 1:\n[Your translation of paragraph 1 here]\n\n"
            f"TRANSLATION OF PARAGRAPH 2:\n[Your translation of paragraph 2 here]\n\n"
            f"... and so on for all {plist_len} paragraphs.\n\n"
            f"You MUST provide EXACTLY {plist_len} translated paragraphs. "
            f"Do not merge, split, or rearrange paragraphs. "
            f"Translate each paragraph independently but consistently. "
            f"Preserve all HTML tags (e.g. <b>, <i>, <a>, <span>) exactly as they appear in the original text. "
            f"Do NOT convert HTML tags to Markdown formatting (e.g. do NOT use **bold** or *italics*). "
            f"Each original paragraph must correspond to exactly one translated paragraph."
        )

        # Update prompt template temporarily
        # Check if it is Gemini (using self.prompt) or others (using self.prompt_template)
        if hasattr(self, "prompt_template"):
             self.prompt_template = structured_prompt + " ```{text}```"
        else:
             self.prompt = structured_prompt + " \n\n{text}"

        try:
            # Call the main translate function of the class
            translated_text = self.translate(formatted_text)
        finally:
            # Restore original prompt template
             if hasattr(self, "prompt_template"):
                 self.prompt_template = original_prompt_template
             else:
                 self.prompt = original_prompt_template

        # Extract translations from structured output
        translated_paragraphs = []
        for i in range(1, plist_len + 1):
            pattern = (
                r"TRANSLATION OF PARAGRAPH "
                + str(i)
                + r":(.*?)(?=TRANSLATION OF.*?\d+:|\Z)"
            )
            matches = re.findall(pattern, translated_text, re.DOTALL)

            if matches:
                translated_paragraph = matches[0].strip()
                translated_paragraphs.append(translated_paragraph)
            else:
                print(f"Warning: Could not find translation for paragraph {i}")
                loose_pattern = (
                    r"(?:TRANSLATION|PARAGRAPH|PARA).*?"
                    + str(i)
                    + r".*?:(.*?)(?=(?:TRANSLATION|PARAGRAPH|PARA).*?\d+.*?:|\Z)"
                )
                loose_matches = re.findall(loose_pattern, translated_text, re.DOTALL)
                if loose_matches:
                    translated_paragraphs.append(loose_matches[0].strip())
                else:
                    translated_paragraphs.append("")

        # If the number of extracted paragraphs is incorrect, try the alternative extraction method.
        if len(translated_paragraphs) != plist_len:
            print(
                f"Warning: Extracted {len(translated_paragraphs)}/{plist_len} paragraphs. Using fallback extraction."
            )

            all_para_pattern = r"(?:TRANSLATION|PARAGRAPH|PARA).*?(\d+).*?:(.*?)(?=(?:TRANSLATION|PARAGRAPH|PARA).*?\d+.*?:|\Z)"
            all_matches = re.findall(all_para_pattern, translated_text, re.DOTALL)

            if all_matches:
                # Create a dictionary to map translation content based on paragraph numbers
                para_dict = {}
                for num_str, content in all_matches:
                    try:
                        num = int(num_str)
                        if 1 <= num <= plist_len:
                            para_dict[num] = content.strip()
                    except ValueError:
                        continue

                # Rebuild the translation list in the original order
                new_translated_paragraphs = []
                for i in range(1, plist_len + 1):
                    if i in para_dict:
                        new_translated_paragraphs.append(para_dict[i])
                    else:
                        new_translated_paragraphs.append("")

                if len(new_translated_paragraphs) == plist_len:
                    translated_paragraphs = new_translated_paragraphs

        if len(translated_paragraphs) < plist_len:
            translated_paragraphs.extend(
                [""] * (plist_len - len(translated_paragraphs))
            )
        elif len(translated_paragraphs) > plist_len:
            translated_paragraphs = translated_paragraphs[:plist_len]

        return translated_paragraphs
