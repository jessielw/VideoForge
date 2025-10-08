from pydantic import BaseModel


class AudioPresetCreate(BaseModel):
    name: str
    description: str
    config: dict
