import itertools
from abc import ABC, abstractmethod


class Base(ABC):
    def __init__(self, key, language) -> None:
        self.keys = itertools.cycle(key.split(","))
        self.language = language

    @abstractmethod
    def rotate_key(self):
        pass

    @abstractmethod
    def translate(self, text):
        pass

    def translate_list(self, text_list):
        return [self.translate(text) for text in text_list]

    def set_deployment_id(self, deployment_id):
        pass
