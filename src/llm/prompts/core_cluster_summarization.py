"""
Pydantic schema for core cluster summarization structured output.
"""

from pydantic import BaseModel, Field


class StructuredOutput(BaseModel):
    """
    Structured output schema for core cluster summarization.

    The LLM will generate a concise summary of a semantic cluster
    identified as containing core/main ideas from a news article.
    """

    summary: str = Field(
        description="Resumen narrativo conciso (2-3 oraciones) del cluster semántico en español. "
                    "Debe ser autocontenido, con tono periodístico profesional, enfocado en hechos principales."
    )
