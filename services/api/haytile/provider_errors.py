"""Shared provider exceptions, independent of API startup order."""


class ProviderError(Exception):
    def __init__(self, code, public_message=None, provider_status=None):
        super().__init__(code)
        self.public_message = public_message
        self.provider_status = provider_status
