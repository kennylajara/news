"""
Pydantic schema for pairwise entity classification structured output.

Defines the response format for 1v1 entity comparison where the LLM
can recommend actions for BOTH entities simultaneously.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class StructuredOutput(BaseModel):
    """
    Structured output for pairwise entity classification.

    The LLM compares two entities and recommends actions for both,
    allowing bidirectional classification updates.
    """

    # Overall relationship assessment
    relationship: Literal['same_entity', 'different_entities', 'ambiguous_usage'] = Field(
        description="Overall relationship: same_entity (one is alias of other), "
                    "different_entities (unrelated), or ambiguous_usage (both refer to multiple things)"
    )

    # Actions for entity_a (the one being evaluated)
    entity_a_action: Literal['make_alias', 'make_canonical', 'make_not_an_entity', 'no_change'] = Field(
        description="Action to take on entity_a: make_alias (of entity_b), make_canonical, "
                    "make_not_an_entity, or no_change"
    )

    # Actions for entity_b (the candidate)
    entity_b_action: Literal['make_alias', 'make_canonical', 'make_not_an_entity', 'no_change'] = Field(
        description="Action to take on entity_b: make_alias (of entity_a), make_canonical, "
                    "make_not_an_entity, or no_change"
    )

    # Confidence level
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence level in the assessment (0.0 = very uncertain, 1.0 = very certain)"
    )

    # Reasoning
    reasoning: str = Field(
        min_length=10,
        max_length=500,
        description="Brief explanation (1-3 sentences) citing evidence from context or co-occurrence"
    )

    # Alternative assessment (if uncertain)
    alternative_relationship: Optional[Literal['same_entity', 'different_entities', 'ambiguous_usage']] = Field(
        default=None,
        description="Alternative relationship if confidence is not very high"
    )

    alternative_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in alternative assessment"
    )
