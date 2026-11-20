from models import ProviderConfig


class KeyRotator:
    def __init__(self, provider: ProviderConfig) -> None:
        self.keys = provider.load_api_keys()
        if not self.keys:
            raise ValueError(f"no keys found in {provider.api_key_env}")
        self.index = 0

    def current(self) -> str:
        return self.keys[self.index]

    def next(self) -> str:
        self.index = (self.index + 1) % len(self.keys)
        return self.current()
