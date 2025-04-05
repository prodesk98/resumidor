from pydantic import BaseModel, Field


class FlashCardSchema(BaseModel):
    question: str = Field(
        ...,
        title="Question",
        description="The card question is related to the front of the card.",
    )
    answer: str = Field(
        ...,
        title="Answer",
        description="The card answer is related to the back of the card.",
    )


class FlashCardSchemaRequest(BaseModel):
    flashcards: list[FlashCardSchema] = Field(
        ...,
        title="Flashcards",
        description="A list of flashcards to be generated. Limit 5 flashcards.",
    )


class SubQueriesResultSchema(BaseModel):
    queries: list[str] = Field(default_factory=list, description="List of sub-queries generated from the original query.")


