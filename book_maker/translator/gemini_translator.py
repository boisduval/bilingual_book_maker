import re
import time
from os import environ
from itertools import cycle

import google.generativeai as genai
from google.generativeai.types.generation_types import (
    StopCandidateException,
    BlockedPromptException,
)
from rich import print

from .base_translator import Base

generation_config = {
    "temperature": 1.0,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 8192,
}

safety_settings = {
    "HATE": "BLOCK_NONE",
    "HARASSMENT": "BLOCK_NONE",
    "SEXUAL": "BLOCK_NONE",
    "DANGEROUS": "BLOCK_NONE",
}

PROMPT_ENV_MAP = {
    "user": "BBM_GEMINIAPI_USER_MSG_TEMPLATE",
    "system": "BBM_GEMINIAPI_SYS_MSG",
}

GEMINIPRO_MODEL_LIST = [
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-pro-001",
    "gemini-1.5-pro-002",
]

GEMINIFLASH_MODEL_LIST = [
    "gemini-2.5-flash",
    "gemini-3-flash",
]


from .batch_strategy import BatchStrategy

class Gemini(BatchStrategy, Base):
    """
    Google gemini translator
    """

    DEFAULT_PROMPT = """You are a professional translator. Your task is to translate the following text into {language}.

CRITICAL RULES:
1. **PRESERVE ALL HTML TAGS**: You MUST keep all HTML tags (like <a>, <b>, <span>, <i>, etc.) and their attributes (like href, class, id) EXACTLY as they are in the source.
2. **DO NOT STRIP TAGS**: Do not remove any tags, even if they seem unnecessary.
3. **TRANSLATE CONTENT ONLY**: Only translate the text nodes inside or between the tags.
4. **NO EXPLANATIONS**: Return ONLY the translated HTML content. Do not add any preamble, conversational filler, or explanations.
5. **MATCH STRUCTURE**: The output HTML structure must be identical to the input HTML structure.

TEXT TO TRANSLATE:
{text}"""

    def __init__(
        self,
        key,
        language,
        prompt_template=None,
        prompt_sys_msg=None,
        context_flag=False,
        temperature=1.0,
        **kwargs,
    ) -> None:
        super().__init__(key, language)
        self.context_flag = context_flag
        self.prompt = (
            prompt_template
            or environ.get(PROMPT_ENV_MAP["user"])
            or self.DEFAULT_PROMPT
        )
        self.prompt_sys_msg = (
            prompt_sys_msg
            or environ.get(PROMPT_ENV_MAP["system"])
            or None  # Allow None, but not empty string
        )
        self.interval = 3
        genai.configure(api_key=next(self.keys))
        generation_config["temperature"] = temperature

    def create_convo(self):
        model = genai.GenerativeModel(
            model_name=self.model,
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=self.prompt_sys_msg,
        )
        self.convo = model.start_chat()
        # print(model)  # Uncomment to debug and inspect the model details.

    def rotate_model(self):
        self.model = next(self.model_list)
        self.create_convo()
        print(f"Using model {self.model}")

    def rotate_key(self):
        genai.configure(api_key=next(self.keys))
        self.create_convo()

    def translate(self, text):
        delay = 1
        exponential_base = 2
        attempt_count = 0
        max_attempts = 7

        t_text = ""
        print(text)
        # same for caiyun translate src issue #279 gemini for #374
        text_list = text.splitlines()
        num = None
        if len(text_list) > 1:
            if text_list[0].isdigit():
                num = text_list[0]

        while attempt_count < max_attempts:
            try:
                self.convo.send_message(
                    self.prompt.format(text=text, language=self.language)
                )
                t_text = self.convo.last.text.strip()
                # 检查是否包含特定标签,如果有则只返回标签内的内容
                tag_pattern = (
                    r"<step3_refined_translation>(.*?)</step3_refined_translation>"
                )
                tag_match = re.search(tag_pattern, t_text, re.DOTALL)
                if tag_match:
                    print(
                        "[bold green]"
                        + re.sub("\n{3,}", "\n\n", t_text)
                        + "[/bold green]"
                    )
                    t_text = tag_match.group(1).strip()
                    # print("[bold green]" + re.sub("\n{3,}", "\n\n", t_text) + "[/bold green]")
                break
            except StopCandidateException as e:
                print(
                    f"Translation failed due to StopCandidateException: {e} Attempting to switch model..."
                )
                self.rotate_model()
            except BlockedPromptException as e:
                print(
                    f"Translation failed due to BlockedPromptException: {e} Attempting to switch model..."
                )
                self.rotate_model()
            except Exception as e:
                print(
                    f"Translation failed due to {type(e).__name__}: {e} Will sleep {delay} seconds"
                )
                time.sleep(delay)
                delay *= exponential_base

                self.rotate_key()
                if attempt_count >= 1:
                    self.rotate_model()

            attempt_count += 1

        if attempt_count == max_attempts:
            print(f"Translation failed after {max_attempts} attempts.")
            return

        if self.context_flag:
            if len(self.convo.history) > 10:
                self.convo.history = self.convo.history[2:]
        else:
            self.convo.history = []

        print("[bold green]" + re.sub("\n{3,}", "\n\n", t_text) + "[/bold green]")
        # for rate limit(RPM)
        time.sleep(self.interval)
        if num:
            t_text = str(num) + "\n" + t_text
        return t_text

    def set_interval(self, interval):
        self.interval = interval

    def set_geminipro_models(self):
        self.set_models(GEMINIPRO_MODEL_LIST)

    def set_geminiflash_models(self):
        self.set_models(GEMINIFLASH_MODEL_LIST)

    def set_models(self, allowed_models):
        available_models = [
            re.sub(r"^models/", "", i.name) for i in genai.list_models()
        ]
        model_list = sorted(
            list(set(available_models) & set(allowed_models)),
            key=allowed_models.index,
        )
        print(f"Using model list {model_list}")
        self.model_list = cycle(model_list)
        self.rotate_model()

    def set_model_list(self, model_list):
        # keep the order of input
        model_list = sorted(list(set(model_list)), key=model_list.index)
        print(f"Using model list {model_list}")
        self.model_list = cycle(model_list)
        self.rotate_model()
