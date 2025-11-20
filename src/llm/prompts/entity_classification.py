"""
Pydantic schema for AI-assisted entity classification.

This schema defines the structured output format that the LLM must return
when analyzing an entity and suggesting its classification.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List


class StructuredOutput(BaseModel):
    """
    Structured output for entity classification suggestions.

    The LLM analyzes an entity mention and its context to determine:
    - Whether it's an alias of another entity
    - Whether it's ambiguous (could refer to multiple entities)
    - Whether it's a canonical entity (standalone)
    - Whether it's not actually an entity (NER false positive)
    """

    classification: Literal['canonical', 'alias', 'ambiguous', 'not_an_entity'] = Field(
        description=(
            "Recommended classification for the entity:\n"
            "- 'canonical': This is a standalone entity (keep as is or it's new)\n"
            "- 'alias': This is a variant/shorthand of another entity\n"
            "- 'ambiguous': Could refer to multiple different entities\n"
            "- 'not_an_entity': Not actually an entity (NER error)"
        )
    )

    canonical_ids: Optional[List[int]] = Field(
        default=None,
        description=(
            "List of canonical entity IDs this entity refers to.\n"
            "- For 'alias': single ID of the canonical entity\n"
            "- For 'ambiguous': multiple IDs of all possible canonical entities\n"
            "- For 'canonical' or 'not_an_entity': null/empty"
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence level from 0.0 to 1.0:\n"
            "- 0.90-1.0: Very high confidence (auto-approve)\n"
            "- 0.70-0.89: High confidence (apply but review)\n"
            "- 0.50-0.69: Medium confidence (suggest for manual review)\n"
            "- 0.0-0.49: Low confidence (leave for manual classification)"
        )
    )

    reasoning: str = Field(
        min_length=10,
        max_length=500,
        description=(
            "Brief explanation (1-3 sentences) of why this classification was chosen.\n"
            "Should reference:\n"
            "- Context from sentences where entity appears\n"
            "- Co-occurrence with candidate entities\n"
            "- Semantic patterns or conventions\n"
            "Example: 'El contexto indica que Luis se refiere al presidente Luis Abinader. "
            "Aparecen juntos en 42 de 45 artículos con términos como presidente y gobierno.'"
        )
    )

    alternative_classification: Optional[Literal['canonical', 'alias', 'ambiguous', 'not_an_entity']] = Field(
        default=None,
        description=(
            "Optional alternative classification if there's uncertainty.\n"
            "Only provide if confidence is between 0.50-0.75 and there's a close second option."
        )
    )

    alternative_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence level for the alternative classification (if provided)"
    )
