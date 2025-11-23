"""
Generic OpenAI client with structured outputs support.
Uses Jinja2 templates for prompts and Pydantic models for response schemas.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from openai import OpenAI
from pydantic import BaseModel
from settings import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MAX_RETRIES, OPENAI_TIMEOUT


# Initialize OpenAI client
client = OpenAI(
    api_key=OPENAI_API_KEY,
    max_retries=OPENAI_MAX_RETRIES,
    timeout=OPENAI_TIMEOUT
)

# Setup Jinja2 environment
PROMPTS_DIR = Path(__file__).parent / 'prompts'
jinja_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True
)


def _load_pydantic_schema(task_name: str) -> type[BaseModel]:
    """
    Dynamically load Pydantic schema from prompts/{task_name}.py.

    Args:
        task_name: Name of the task (e.g., 'core_cluster_summarization')

    Returns:
        Pydantic BaseModel class named 'StructuredOutput'

    Raises:
        FileNotFoundError: If schema file doesn't exist
        ImportError: If StructuredOutput class not found in module
    """
    schema_file = PROMPTS_DIR / f"{task_name}.py"

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    # Load module dynamically
    spec = importlib.util.spec_from_file_location(f"prompts.{task_name}", schema_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {schema_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[f"prompts.{task_name}"] = module
    spec.loader.exec_module(module)

    # Get StructuredOutput class
    if not hasattr(module, 'StructuredOutput'):
        raise ImportError(f"'StructuredOutput' class not found in {schema_file}")

    schema_class = getattr(module, 'StructuredOutput')

    if not issubclass(schema_class, BaseModel):
        raise TypeError(f"'StructuredOutput' must be a Pydantic BaseModel subclass")

    return schema_class


def _render_prompts(task_name: str, data: Dict[str, Any]) -> tuple[str, str]:
    """
    Render system and user Jinja2 templates with provided data.

    Args:
        task_name: Name of the task (e.g., 'core_cluster_summarization')
        data: Dictionary with variables to render in templates

    Returns:
        Tuple of (system_prompt, user_prompt) rendered strings

    Raises:
        TemplateNotFound: If template files don't exist
    """
    system_template_name = f"{task_name}_system_prompt.md.jinja"
    user_template_name = f"{task_name}_user_prompt.md.jinja"

    try:
        system_template = jinja_env.get_template(system_template_name)
        system_prompt = system_template.render(**data)
    except TemplateNotFound:
        raise FileNotFoundError(f"System template not found: {PROMPTS_DIR / system_template_name}")

    try:
        user_template = jinja_env.get_template(user_template_name)
        user_prompt = user_template.render(**data)
    except TemplateNotFound:
        raise FileNotFoundError(f"User template not found: {PROMPTS_DIR / user_template_name}")

    return system_prompt, user_prompt


def openai_structured_output(
    task_name: str,
    data: Dict[str, Any],
    model: str = None,
    validation_context: Dict[str, Any] = None
) -> BaseModel:
    """
    Generic wrapper for OpenAI structured outputs.

    Loads system/user Jinja templates and Pydantic schema based on task_name,
    renders the prompts with data, and calls OpenAI API with structured outputs.

    Directory structure expected:
        src/llm/prompts/{task_name}_system_prompt.md.jinja  - System prompt template
        src/llm/prompts/{task_name}_user_prompt.md.jinja    - User prompt template
        src/llm/prompts/{task_name}.py                      - Pydantic schema with 'StructuredOutput' class

    Args:
        task_name: Name of the task (e.g., 'core_cluster_summarization')
        data: Dictionary with variables for template rendering
        model: OpenAI model to use (defaults to OPENAI_MODEL from settings)
        validation_context: Optional context for Pydantic validators (e.g., valid entity IDs)

    Returns:
        Pydantic model instance with parsed structured output

    Raises:
        FileNotFoundError: If template or schema file not found
        ImportError: If schema module or class not found
        OpenAI API errors: If API call fails

    Example:
        >>> data = {'title': 'Article Title', 'cluster_sentences': ['...'], 'cluster_score': 0.85}
        >>> result = openai_structured_output('core_cluster_summarization', data)
        >>> print(result.summary)

        >>> # With validation context
        >>> result = openai_structured_output(
        ...     'entity_pairwise_classification',
        ...     data,
        ...     validation_context={'valid_entity_ids': [123, 456]}
        ... )
    """
    from llm.logging import log_llm_api_call

    # Load schema and templates
    schema_class = _load_pydantic_schema(task_name)
    system_prompt, user_prompt = _render_prompts(task_name, data)

    # Use provided model or default from settings
    model_name = model or OPENAI_MODEL

    # Extract context data for logging
    context_data = {
        'task_name': task_name,
        'data_keys': list(data.keys()),
    }

    # Add relevant IDs if present
    if 'article_id' in data:
        context_data['article_id'] = data['article_id']
    if 'entity_a_id' in data:
        context_data['entity_a_id'] = data['entity_a_id']
    if 'entity_b_id' in data:
        context_data['entity_b_id'] = data['entity_b_id']
    if 'entity_id' in data:
        context_data['entity_id'] = data['entity_id']

    # Use logging context manager
    with log_llm_api_call('structured_output', model_name, task_name, context_data) as logger:
        # Set prompts
        logger.set_prompts(system_prompt, user_prompt)

        # Call OpenAI API with structured outputs
        completion = client.beta.chat.completions.parse(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=schema_class
        )

        # Set response for logging
        logger.set_response(completion)

        # Parse the structured output
        parsed = completion.choices[0].message.parsed

        if parsed is None:
            raise ValueError("OpenAI API returned None for parsed output")

        # If validation context provided, validate with context
        if validation_context:
            # Re-validate with context (Pydantic validators will use info.context)
            parsed = schema_class.model_validate(
                parsed.model_dump(),
                context=validation_context
            )

        # Set parsed output for logging
        logger.set_parsed_output(parsed.model_dump())

        return parsed
