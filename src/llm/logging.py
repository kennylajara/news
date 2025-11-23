"""
LLM API call logging system.

Provides context manager and logger class for tracking all LLM API calls,
including prompts, responses, tokens, timing, and errors.
"""

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional, List
import json


class LLMApiCallLogger:
    """
    Logger for LLM API calls.

    Tracks all relevant information about an API call including prompts,
    responses, tokens, timing, and errors.
    """

    def __init__(
        self,
        call_type: str,
        model: str,
        task_name: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize logger.

        Args:
            call_type: Type of API call ('structured_output', 'chat_completion', etc.)
            model: Model name ('gpt-5-nano', 'gpt-4o', etc.)
            task_name: Optional task name ('article_analysis', etc.)
            context_data: Optional metadata for filtering (article_id, entity_id, etc.)
        """
        self.call_type = call_type
        self.model = model
        self.task_name = task_name
        self.context_data = context_data or {}

        # Timing
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.duration_seconds: Optional[float] = None

        # Prompts
        self.system_prompt: Optional[str] = None
        self.user_prompt: Optional[str] = None
        self.messages: Optional[List[Dict[str, str]]] = None

        # Response
        self.response_raw: Optional[Dict] = None
        self.parsed_output: Optional[Dict] = None

        # Tokens
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.total_tokens: Optional[int] = None

        # Status
        self.success: bool = True
        self.error_message: Optional[str] = None

    def set_prompts(self, system_prompt: str, user_prompt: str):
        """Set system and user prompts for structured outputs."""
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

    def set_messages(self, messages: List[Dict[str, str]]):
        """Set messages array for chat completions."""
        self.messages = messages

    def set_response(self, response):
        """
        Set OpenAI API response and extract tokens.

        Args:
            response: OpenAI API response object (ChatCompletion or ParsedChatCompletion)
        """
        # Convert response to dict for JSON serialization
        self.response_raw = response.model_dump() if hasattr(response, 'model_dump') else dict(response)

        # Extract token usage
        if hasattr(response, 'usage') and response.usage:
            self.input_tokens = response.usage.prompt_tokens
            self.output_tokens = response.usage.completion_tokens
            self.total_tokens = response.usage.total_tokens

    def set_parsed_output(self, parsed_output: Dict):
        """Set parsed structured output (Pydantic model dump)."""
        self.parsed_output = parsed_output

    def mark_success(self):
        """Mark call as successful and calculate duration."""
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.success = True

    def mark_error(self, error_message: str):
        """Mark call as failed with error message."""
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.success = False
        self.error_message = error_message

    def save(self):
        """
        Save log entry to separate logs database.

        Uses a completely separate database (data/llm_logs.db) to avoid
        any conflicts with the main application database transactions.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from db.models import Base, LLMApiCall
        from pathlib import Path

        # Ensure data directory exists
        Path("data").mkdir(parents=True, exist_ok=True)

        # Create separate engine for logs database
        engine = create_engine('sqlite:///data/llm_logs.db', echo=False)

        # Create tables if they don't exist
        Base.metadata.create_all(engine)

        # Create session
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        try:
            # Create log entry
            log_entry = LLMApiCall(
                call_type=self.call_type,
                task_name=self.task_name,
                model=self.model,
                started_at=self.started_at,
                completed_at=self.completed_at,
                duration_seconds=self.duration_seconds,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                total_tokens=self.total_tokens,
                system_prompt=self.system_prompt,
                user_prompt=self.user_prompt,
                messages=self.messages,
                response_raw=self.response_raw,
                parsed_output=self.parsed_output,
                success=1 if self.success else 0,
                error_message=self.error_message,
                context_data=self.context_data if self.context_data else None
            )

            session.add(log_entry)
            session.commit()

        except Exception as e:
            # Silently fail - logging shouldn't crash the main application
            session.rollback()
            import sys
            print(f"Warning: Failed to save LLM API call log: {e}", file=sys.stderr)

        finally:
            session.close()
            engine.dispose()


@contextmanager
def log_llm_api_call(
    call_type: str,
    model: str,
    task_name: Optional[str] = None,
    context_data: Optional[Dict[str, Any]] = None
):
    """
    Context manager for logging LLM API calls.

    Automatically handles success/error tracking and database persistence.

    Args:
        call_type: Type of API call ('structured_output', 'chat_completion', etc.)
        model: Model name ('gpt-5-nano', 'gpt-4o', etc.)
        task_name: Optional task name ('article_analysis', etc.)
        context_data: Optional metadata for filtering

    Yields:
        LLMApiCallLogger instance

    Example:
        >>> with log_llm_api_call('structured_output', 'gpt-5-nano', 'article_analysis') as logger:
        ...     logger.set_prompts(system_prompt, user_prompt)
        ...     result = client.beta.chat.completions.parse(...)
        ...     logger.set_response(result)
        ...     logger.set_parsed_output(parsed.model_dump())
    """
    logger = LLMApiCallLogger(call_type, model, task_name, context_data)

    try:
        yield logger
        logger.mark_success()
    except Exception as e:
        logger.mark_error(str(e))
        raise
    finally:
        logger.save()
