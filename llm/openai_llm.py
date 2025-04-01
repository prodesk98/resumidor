from typing import List

from langchain_core.messages import HumanMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    PromptTemplate
)
from langchain_openai import ChatOpenAI
from openai import OpenAI, Stream
from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE,
    OPENAI_EMBEDDING_MODEL,
)
from prompt_engineering import SUMMARIZER_PROMPT, FLASHCARD_PROMPT
from schemas import FlashCardSchema, FlashCardSchemaRequest
from .base import BaseLLM, BaseEmbedding
from .tools import Tools

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)


class OpenAILLM(BaseLLM):
    """
    OpenAI LLM wrapper for the OpenAI API.
    """

    def __init__(self, namespace: str):
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        self._tools = Tools(namespace)
        self.structured = ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
        )

    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def generate(self, messages: list[dict]) -> Stream:
        return self._client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "developer", "content": SUMMARIZER_PROMPT},
            ] + messages,
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
            stream=True,
        )

    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def flashcard(self, prompt: str) -> List[FlashCardSchema]:
        """
        Generate flashcards based on the provided prompt.
        :param prompt:
        :return:
        """
        # Create a structured prompt for the flashcard generation
        system_prompt = ChatPromptTemplate.from_messages(
            messages=[
                SystemMessagePromptTemplate(
                    prompt=PromptTemplate(
                        template=FLASHCARD_PROMPT,
                        input_variables=[],
                    )
                ),
                HumanMessage(
                    content=prompt,
                ),
            ]
        )
        #

        # Generate the flashcards using the structured prompt
        structured_schema = self.structured.with_structured_output(FlashCardSchemaRequest, method="json_schema")
        #

        # Create the chain to process the structured prompt
        chain = (
            system_prompt |
            structured_schema
        )
        #

        # Execute the chain and return the flashcards
        output: FlashCardSchemaRequest = chain.invoke({})
        #
        return output.flashcards


class EmbeddingOpenAI(BaseEmbedding):
    """
    OpenAI LLM wrapper for the OpenAI API.
    """

    def __init__(self):
        self._client = OpenAI(api_key=OPENAI_API_KEY)

    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def embed(self, text: str) -> List[float]:
        """
        Generate embeddings for the provided text using the OpenAI API.
        :param text:
        :return:
        """
        return self._client.embeddings.create(
            input=text,
            model=OPENAI_EMBEDDING_MODEL,
        ).data[0].embedding
