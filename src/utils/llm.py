"""Helper functions for LLM"""

import json
from langchain_core.messages import SystemMessage
from pydantic import BaseModel
from src.llm.models import get_model, get_model_info
from src.utils.progress import progress
from src.graph.state import AgentState


def _add_russian_instruction(prompt):
    """Add Russian language instruction to the system message."""
    if hasattr(prompt, 'to_messages'):
        messages = prompt.to_messages()
    elif isinstance(prompt, list):
        messages = prompt
    else:
        return prompt

    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage) and "русском" not in msg.content.lower():
            messages[i] = SystemMessage(
                content=msg.content + "\n\nIMPORTANT: Write your reasoning in Russian language. Keep signal values (bullish/bearish/neutral) in English."
            )
            break

    return messages


def call_llm(
    prompt: any,
    pydantic_model: type[BaseModel],
    agent_name: str | None = None,
    state: AgentState | None = None,
    max_retries: int = 3,
    default_factory=None,
) -> BaseModel:
    """
    Makes an LLM call with retry logic, handling both JSON supported and non-JSON supported models.

    Args:
        prompt: The prompt to send to the LLM
        pydantic_model: The Pydantic model class to structure the output
        agent_name: Optional name of the agent for progress updates and model config extraction
        state: Optional state object to extract agent-specific model configuration
        max_retries: Maximum number of retries (default: 3)
        default_factory: Optional factory function to create default response on failure

    Returns:
        An instance of the specified Pydantic model
    """

    # Extract model configuration if state is provided and agent_name is available
    if state and agent_name:
        model_name, model_provider = get_agent_model_config(state, agent_name)
    else:
        # Use system defaults when no state or agent_name is provided
        model_name = "gpt-4.1"
        model_provider = "OPENAI"

    # Extract API keys from state if available
    api_keys = None
    if state:
        request = state.get("metadata", {}).get("request")
        if request and hasattr(request, 'api_keys'):
            api_keys = request.api_keys

    model_info = get_model_info(model_name, model_provider)
    llm = get_model(model_name, model_provider, api_keys)

    # For non-JSON support models, we can use structured output
    if not (model_info and not model_info.has_json_mode()):
        llm = llm.with_structured_output(
            pydantic_model,
            method="json_mode",
        )

    # Add Russian language instruction to system messages
    messages = _add_russian_instruction(prompt)

    # Call the LLM with retries
    last_error = None
    for attempt in range(max_retries):
        try:
            # Call the LLM
            result = llm.invoke(messages)

            # For non-JSON support models, we need to extract and parse the JSON manually
            if model_info and not model_info.has_json_mode():
                parsed_result = extract_json_from_response(result.content)
                if parsed_result:
                    return pydantic_model(**parsed_result)
            else:
                return result

        except Exception as e:
            last_error = e
            if agent_name:
                progress.update_status(agent_name, None, f"Error - retry {attempt + 1}/{max_retries}")

            if attempt == max_retries - 1:
                error_msg = f"{type(e).__name__}: {e}"
                print(f"Error in LLM call after {max_retries} attempts: {error_msg}")
                # Use default_factory if provided, otherwise create with error info
                if default_factory:
                    return default_factory()
                return create_default_response(pydantic_model, error_msg)

    # This should never be reached due to the retry logic above
    if default_factory:
        return default_factory()
    return create_default_response(pydantic_model, str(last_error) if last_error else "")


def create_default_response(model_class: type[BaseModel], error_msg: str = "") -> BaseModel:
    """Creates a safe default response based on the model's fields."""
    default_values = {}
    for field_name, field in model_class.model_fields.items():
        if field.annotation == str:
            default_values[field_name] = f"Ошибка: {error_msg}" if error_msg else "Ошибка анализа"
        elif field.annotation == float:
            default_values[field_name] = 0.0
        elif field.annotation == int:
            default_values[field_name] = 0
        elif hasattr(field.annotation, "__origin__") and field.annotation.__origin__ == dict:
            default_values[field_name] = {}
        else:
            # For other types (like Literal), try to use the first allowed value
            if hasattr(field.annotation, "__args__"):
                default_values[field_name] = field.annotation.__args__[0]
            else:
                default_values[field_name] = None

    return model_class(**default_values)


def extract_json_from_response(content: str) -> dict | None:
    """Extracts JSON from markdown-formatted or plain JSON response."""
    # Try ```json ... ``` block first
    try:
        json_start = content.find("```json")
        if json_start != -1:
            json_text = content[json_start + 7 :]  # Skip past ```json
            json_end = json_text.find("```")
            if json_end != -1:
                json_text = json_text[:json_end].strip()
                return json.loads(json_text)
    except Exception as e:
        print(f"Error extracting JSON from response: {e}")

    # Fallback: try parsing the entire content as JSON
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: find first { ... } with brace matching
    try:
        start = content.index("{")
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(content[start:i+1])
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    return None


def get_agent_model_config(state, agent_name):
    """
    Get model configuration for a specific agent from the state.
    Falls back to global model configuration if agent-specific config is not available.
    Always returns valid model_name and model_provider values.
    """
    request = state.get("metadata", {}).get("request")
    
    if request and hasattr(request, 'get_agent_model_config'):
        # Get agent-specific model configuration
        model_name, model_provider = request.get_agent_model_config(agent_name)
        # Ensure we have valid values
        if model_name and model_provider:
            return model_name, model_provider.value if hasattr(model_provider, 'value') else str(model_provider)
    
    # Fall back to global configuration (system defaults)
    model_name = state.get("metadata", {}).get("model_name") or "gpt-4.1"
    model_provider = state.get("metadata", {}).get("model_provider") or "OPENAI"
    
    # Convert enum to string if necessary
    if hasattr(model_provider, 'value'):
        model_provider = model_provider.value
    
    return model_name, model_provider
