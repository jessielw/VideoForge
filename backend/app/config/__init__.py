import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    API_PREFIX: str = "/api"
    # DEBUG: bool = False
    ALLOWED_ORIGINS: list = field(default_factory=list)

    def __post_init__(self) -> None:
        # update allowed origins (defaults to everything)
        get_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
        if get_allowed_origins:
            self.ALLOWED_ORIGINS.extend(get_allowed_origins.split(","))


settings = Settings()
