"""
Pydantic schema for pairwise entity classification structured output.

Defines the response format for 1v1 entity comparison where the LLM
can recommend classification changes and reference modifications for
BOTH entities simultaneously.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List


class EntityClassificationChange(BaseModel):
    """Classification change for an entity."""
    entity_id: int = Field(description="ID of entity to classify")
    classification: Literal['alias', 'ambiguous', 'canonical', 'not_an_entity'] = Field(
        description="What this entity's classification should be"
    )


class EntityReferenceChange(BaseModel):
    """Change to an entity's canonical references."""
    entity_id: int = Field(description="ID of entity whose references to modify")
    add_refs: Optional[List[int]] = Field(
        default=None,
        description="Canonical IDs to ADD to this entity's references"
    )
    remove_refs: Optional[List[int]] = Field(
        default=None,
        description="Canonical IDs to REMOVE from this entity's references"
    )


class StructuredOutput(BaseModel):
    """Structured output for pairwise entity classification."""

    # Classification changes (exactly 2: one for entity_a, one for entity_b)
    classification_changes: List[EntityClassificationChange] = Field(
        min_length=2,
        max_length=2,
        description="Classification changes for both entities (exactly 2: entity_a and entity_b)"
    )

    # Reference changes
    reference_changes: Optional[List[EntityReferenceChange]] = Field(
        default=None,
        description="Changes to canonical references (for ALIAS/AMBIGUOUS classifications)"
    )

    # Confidence and reasoning
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence (0.0 = totally uncertain, 1.0 = totally certain)"
    )
    reasoning: str = Field(
        min_length=10,
        max_length=500,
        description="Brief explanation (1-3 sentences) citing evidence from context"
    )

    @field_validator('classification_changes')
    @classmethod
    def validate_entity_ids(cls, v, info):
        """Validate that entity IDs match the entities being compared."""
        # valid_entity_ids should be passed via validation_context
        valid_ids = info.context.get('valid_entity_ids', []) if info.context else []

        if valid_ids:
            entity_ids = [change.entity_id for change in v]

            # Check all IDs are valid
            for eid in entity_ids:
                if eid not in valid_ids:
                    raise ValueError(f"Entity ID {eid} not in valid IDs {valid_ids}")

            # Ensure both IDs are present and unique
            if len(set(entity_ids)) != 2:
                raise ValueError("Must have exactly 2 unique entity IDs")

            # Ensure we have exactly the two expected IDs
            if set(entity_ids) != set(valid_ids):
                raise ValueError(f"Entity IDs {entity_ids} don't match expected {valid_ids}")

        return v
