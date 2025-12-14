# Provider Routing Configuration

**Session 73** - Refactored provider routing to use centralized configuration

## Overview

Replaced hard-coded if/elif chains with declarative `TASK_PROVIDER_CONFIG` dictionary. This makes provider routing easier to maintain, test, and modify.

## Architecture

### Before (Hard-coded)

```python
def get_provider_for_task(task_type: str):
    if task_type == 'navigation':
        if os.getenv('OPENAI_API_KEY'):
            return get_provider('openai')
        elif os.getenv('GOOGLE_API_KEY'):
            return get_provider('google')
        # ... 8 more lines
    elif task_type == 'research':
        if os.getenv('GOOGLE_API_KEY'):
            return get_provider('google')
        # ... 6 more lines
    # ... 60 more lines of if/elif
```

**Problems:**
- ❌ Repeated environment checks
- ❌ Hard-coded model names
- ❌ Comments as documentation
- ❌ Hard to test/modify

### After (Config-based)

```python
TASK_PROVIDER_CONFIG = {
    'navigation': {
        'priority': ['openai', 'google', 'groq-responses'],
        'reason': 'OpenAI has reliable structured outputs',
        'fallback_model': 'openai'
    },
    'long_document': {
        'priority': ['google:gemini-1.5-pro-latest', 'anthropic', 'openai'],
        'reason': 'Need 2M context window',
        'fallback_model': 'openai'
    },
    # ... more tasks
}

def get_provider_for_task(task_type: str):
    config = TASK_PROVIDER_CONFIG.get(task_type)
    for provider_spec in config['priority']:
        if is_provider_available(provider_spec):
            return get_provider_with_model(provider_spec)
    return get_provider(config['fallback_model'])
```

**Benefits:**
- ✅ Single source of truth
- ✅ Self-documenting (reason field)
- ✅ Model override support (`provider:model`)
- ✅ Easy to test/modify
- ✅ DRY (no repeated checks)

## Current Configuration

### Task Routing Table

| Task Type | Priority Chain | Reason |
|-----------|---------------|---------|
| **navigation** | openai → google → groq | OpenAI has reliable structured outputs (Session 73) |
| **explain** | openai → google → groq | Same as navigation |
| **research** | google → anthropic → openai | Gemini Flash is 85% cheaper |
| **long_document** | google:gemini-1.5-pro → anthropic → openai | Need 2M context window |
| **draft** | openai | Proven quality for civic comments |
| **conversational** | anthropic → openai → google | Quality priority for function calling |
| **realtime_research** | perplexity → google → openai | Perplexity has built-in web search |

### Cost Optimization

The config enables intelligent cost vs. quality trade-offs:

- **Cheap tasks** (research, explain) → Gemini Flash ($0.075/1M tokens)
- **Complex tasks** (navigation, draft) → OpenAI ($0.60/1M tokens)
- **Long documents** → Gemini Pro 1.5 ($1.25/1M tokens, 2M context)
- **High quality** (conversational) → Claude Sonnet 4 ($3.00/1M tokens)

**Current costs:** <$7/month total

## API

### Core Functions

```python
# Get provider for specific task
provider = get_provider_for_task('navigation')
# Returns: OpenAIProvider instance

# Check if provider is available
is_available = is_provider_available('google')
# Returns: True if GOOGLE_API_KEY is set

# Get provider with model override
provider = get_provider_with_model('google', 'gemini-1.5-pro-latest')
# Returns: GoogleProvider configured with Pro model
```

### Model Override Notation

The config supports `provider:model` notation for model-specific routing:

```python
'long_document': {
    'priority': ['google:gemini-1.5-pro-latest', 'anthropic', 'openai'],
    # ... ^^^ Uses Gemini Pro 1.5 for 2M context window
}
```

## Modifying Provider Routing

### Example: Test Groq for Navigation

```python
TASK_PROVIDER_CONFIG = {
    'navigation': {
        'priority': ['groq-responses', 'openai', 'google'],  # Groq first
        'reason': 'Testing Groq Responses API (Session 73)',
        'fallback_model': 'openai'
    },
}
```

### Example: Add New Task Type

```python
TASK_PROVIDER_CONFIG = {
    'summarization': {
        'priority': ['google', 'openai'],
        'reason': 'Cheap + fast for simple summarization',
        'fallback_model': 'openai'
    },
}
```

## Testing

Run validation tests:

```bash
# Test config structure and routing
python scripts/test_provider_config.py

# Test backward compatibility (navigation)
python scripts/test_jurisdiction_reference.py
```

## Future Improvements

1. **Externalize config** - Move to YAML/JSON for runtime modification
2. **Cost tracking** - Add actual cost per task type
3. **A/B testing** - Support percentage-based routing
4. **Performance metrics** - Track latency/success rate per provider
5. **Auto-fallback** - Automatically fallback on errors

## Migration Notes

**Breaking changes:** None - API is backward compatible

**Behavior changes:** None - routing logic preserved exactly

**File modified:** `src/llm_provider.py` (~100 lines added, ~95 lines removed)

## Related Documentation

- `docs/core/LLM_PROVIDER_ARCHITECTURE.md` - Overall provider architecture
- `tests/test_provider_abstraction.py` - Provider interface tests
- `tests/test_cost_optimization.py` - Cost optimization validation
