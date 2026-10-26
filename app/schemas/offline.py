from pydantic import BaseModel

from app.schemas.content import QuestionWithAnswerOut, TopicOut


class OfflinePackOut(BaseModel):
    """Everything practice needs without a connection: topics and every active question with its answer."""

    version: str
    topics: list[TopicOut]
    questions: list[QuestionWithAnswerOut]
