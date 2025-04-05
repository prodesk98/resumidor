from datetime import datetime
from typing import List, Any, Optional, TypeVar
from uuid import UUID

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    PromptTemplate,
    MessagesPlaceholder,
)
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from streamlit.delta_generator import DeltaGenerator

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE, OPENAI_API_BASE, NATURAL_LANGUAGE,
)
from loggings import logger
from prompt_engineering import SUMMARIZER_PROMPT, FLASHCARD_PROMPT
from schemas import FlashCardSchema, FlashCardSchemaRequest
from exceptions import (
    GoogleSearchError, SemanticSearchError,
    ArxivSearchError, WebParserParserError,
    YoutubeParserError, GenerativeError
)
from .base import BaseLLM
from .tools import Tools

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)


T = TypeVar("T", bound=BaseModel)


class AgentCallbackHandler(BaseCallbackHandler):
    def __init__(self, placeholder: Optional[DeltaGenerator]):
        self._placeholder = placeholder
        self._feedback_text = ""
        self.actions: dict[str, str] = {}

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._feedback_text += f"\n\n⚙️ Agent action: {action.tool} with input: {action.tool_input}"
        self.actions[run_id.hex] = action.tool
        if self._placeholder:
            self._placeholder.markdown(self._feedback_text)


    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        if len(self.actions) == 0:
            return
        self._feedback_text += f"\n\n✅ Agent finished"
        if self._placeholder:
            self._placeholder.markdown(self._feedback_text)


class OpenAILLM(BaseLLM):
    """
    OpenAI LLM wrapper for the OpenAI API.
    """

    def __init__(self, namespace: Optional[str] = None):
        self._namespace = namespace or "default"
        self._tools = Tools(self._namespace)
        self.structured_llm = ChatOpenAI(
            base_url=OPENAI_API_BASE,
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
        )
        self.agent_llm = ChatOpenAI(
            base_url=OPENAI_API_BASE,
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
        )


    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def generate(self, chat_history: list[BaseMessage], placeholder: Optional[DeltaGenerator] = None) -> str:
        """
        Generate a response based on the provided chat history.
        :param chat_history:
        :param placeholder:
        :return:
        """
        logger(
            " ".join(
                [
                    f"[{self._namespace}] Starting agent generation...",
                    f"tools: {len(self._tools.get())}",
                    f"chat: {len(chat_history)}",
                ]
            ),
            level="info",
        )
        # System template
        template = (
            SUMMARIZER_PROMPT
            .replace("{{current_time}}", datetime.now().strftime("%m-%d-%Y %H:%M:%S")) # Replace current time if have it.
            .replace("{{natural_language}}", NATURAL_LANGUAGE) # Replace natural language if have it.
        )
        # Generate messages structure
        messages = [
            SystemMessage(template),
            MessagesPlaceholder(variable_name="chat_history"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
        #
        # Construct the prompt for the agent
        prompt = ChatPromptTemplate.from_messages(messages=messages)
        #

        # Create Agent Executor
        agent = create_tool_calling_agent(self.agent_llm, self._tools.get(), prompt)
        #

        # Create the agent executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self._tools.get(),
            verbose=True,
            max_iterations=15,
            early_stopping_method="force",
            handle_parsing_errors=True,
            return_intermediate_steps=True,
            callbacks=[AgentCallbackHandler(placeholder)] if placeholder else None,
        )
        #

        try:
            result: dict = agent_executor.invoke(
                {
                    "chat_history": chat_history,
                    "agent_scratchpad": [],
                }
            )
            return result.get("output", "")
        except GoogleSearchError as e:
            return e.message
        except SemanticSearchError as e:
            return e.message
        except ArxivSearchError as e:
            return e.message
        except WebParserParserError as e:
            return e.message
        except YoutubeParserError as e:
            return e.message
        except Exception as e:
            return f"An error occurred: {e}"


    def _generate_structured_output(self, template: str, prompt: str, schema: type[T], inputs: dict) -> T:
        system_prompt = ChatPromptTemplate.from_messages(
            messages=[
                SystemMessagePromptTemplate(
                    prompt=PromptTemplate(
                        template=template,
                        input_variables=[k for k in inputs.keys()],
                    )
                ),
                HumanMessage(
                    content=prompt,
                ),
            ]
        )

        structured_schema = self.structured_llm.with_structured_output(schema, method="json_schema")

        chain = (
            system_prompt |
            structured_schema
        )

        try:
            output: schema = chain.invoke(inputs)
            return output
        except Exception as e:
            raise GenerativeError(str(e)) from e


    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def flashcard(self, prompt: str, quantities: int = 5) -> List[FlashCardSchema]:
        """
        Generate flashcards based on the provided prompt.
        :param prompt:
        :param quantities:
        :return:
        """
        template = (
            FLASHCARD_PROMPT.replace("{{natural_language}}", NATURAL_LANGUAGE)  # Replace natural language if have it.
        )

        output = self._generate_structured_output(
            template=template,
            prompt=prompt,
            schema=FlashCardSchemaRequest,
            inputs={
                "quantities": quantities,
            },
        )

        return output.flashcards


    def generate_sub_queries(self, query: str) -> list[str]:
        """
        Generate sub-queries based on the provided query.
        :param query:
        :return:
        """


    def reflection(self, query: str, sub_queries: list[str], chunks: list[str]) -> str:
        """
        Generate a reflection based on the provided query, sub-queries, and chunks.
        :param query:
        :param sub_queries:
        :param chunks:
        :return:
        """

