from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
