from models import ModelConfig, ModelsConfig, ProviderConfig

def pick_model(path: str, model_name: str | None = None) -> tuple[ProviderConfig, ModelConfig]:
    config = ModelsConfig.from_json_file(path)
    name = model_name or config.default_model
    for provider_name in [config.default_provider, *config.fallback_order]:
        provider = config.providers[provider_name]
        model = provider.get_model(name)
        if model is not None:
            return provider, model
    raise ValueError(f"model '{name}' not found in {path}")
