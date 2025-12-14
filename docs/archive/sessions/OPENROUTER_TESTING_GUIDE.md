# OpenRouter Integration Testing Guide

**Session 78 - Interactive Testing Instructions**

This guide walks you through testing the OpenRouter integration both with and without a real API key.

---

## Quick Start (No API Key Required)

Test the integration without making real API calls:

```bash
# From project root
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

# Run automated tests (no API calls)
python tests/test_openrouter_integration.py

# Run interactive menu (dry-run mode)
python scripts/test_openrouter_interactive.py
```

**Expected output**: All tests pass, showing OpenRouter is properly integrated.

---

## Full Testing (With OpenRouter API Key)

### Step 1: Get OpenRouter API Key

1. Go to https://openrouter.ai/keys
2. Sign up or log in (GitHub/Google auth available)
3. Create a new API key
4. Copy the key (starts with `sk-or-...`)

**Note**: OpenRouter offers:
- **Free tier**: Gemini 2.0 Flash (zero cost for testing)
- **Pay-as-you-go**: Only charged for what you use
- **$0 minimum**: No upfront cost required

### Step 2: Configure Environment

```bash
# Set the API key
export OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY-HERE"

# Optional: Track usage in OpenRouter dashboard
export OPENROUTER_APP_NAME="civic-conversational-os-testing"
export OPENROUTER_SITE_URL="https://github.com/YOUR-USERNAME/civic"

# Verify it's set
echo $OPENROUTER_API_KEY
```

### Step 3: Run Interactive Tests

```bash
python scripts/test_openrouter_interactive.py
```

**Test menu**:
```
1. Provider Instantiation (dry-run, always safe)
2. Model Registry (dry-run, always safe)
3. Task Routing Configuration (dry-run, always safe)
4. Automatic Model Selection (dry-run, always safe)
5. Simple Completion (⚠️ REAL API CALL - uses free tier)
6. Chat Routing Integration (⚠️ REAL API CALL - uses free tier)
7. Cost Comparison (dry-run, always safe)
```

**Recommended testing sequence**:
1. Run tests 1-4 first (no API calls, validates configuration)
2. Run test 7 to see cost comparison
3. Run test 5 for a simple API call (uses **free** Gemini tier, $0 cost)
4. Run test 6 for full chat routing test (uses **free** Gemini tier, $0 cost)

### Step 4: Manual Python Testing

Open an interactive Python session:

```bash
python
```

#### Test 1: Check Provider Availability

```python
import os
import sys
sys.path.insert(0, 'src')

from llm_provider import is_provider_available, list_available_providers

# Check if OpenRouter is available
print("OpenRouter available:", is_provider_available('openrouter'))

# List all available providers
print("All providers:", list_available_providers())
# Expected: ['openai', 'ollama', 'openrouter'] (if key is set)
```

#### Test 2: Get OpenRouter Provider

```python
from llm_provider import get_provider

# Get OpenRouter provider
provider = get_provider('openrouter')

print("Provider name:", provider.name)  # Should be 'openrouter'
print("Default model:", provider.default_model)  # Should be 'meta-llama/llama-3.3-70b-instruct'
```

#### Test 3: Test Model Registry

```python
from model_registry import get_models_by_provider, get_model_info

# Get all OpenRouter models
openrouter_models = get_models_by_provider('openrouter')
print(f"OpenRouter models: {len(openrouter_models)}")  # Should be 5

# Check the free tier model
free_model = get_model_info('google/gemini-2.0-flash-exp:free')
print(f"Free tier cost: ${free_model['cost_per_1m_tokens']}/1M")  # Should be $0.00
```

#### Test 4: Test Task Routing

```python
from llm_provider import get_model_for_task

# Get model for query planning (should prefer free tier)
provider = get_model_for_task('query_planning')
print("Query planning model:", provider.default_model)
# Expected: 'google/gemini-2.0-flash-exp:free' (if OpenRouter available)

# Get model for conversational (should prefer Claude)
provider = get_model_for_task('conversational')
print("Conversational model:", provider.default_model)
# Expected: 'anthropic/claude-3.5-sonnet' (if OpenRouter available)
```

#### Test 5: Simple Completion (⚠️ Real API Call)

**Note**: This uses the **free tier** - zero cost!

```python
from llm_provider import get_provider

# Get OpenRouter with free tier model
provider = get_provider('openrouter')
provider._default_model = 'google/gemini-2.0-flash-exp:free'

# Make a simple completion
result = provider.complete(
    messages=[
        {"role": "user", "content": "Say 'Hello from OpenRouter!' in exactly 5 words."}
    ],
    max_tokens=50
)

print("Response:", result.content)
print("Tokens used:", result.usage.get('total_tokens', 'N/A'))
print("Cost: $0 (free tier)")
```

**Expected output**: A short response using the free Gemini model.

#### Test 6: Chat Routing Integration (⚠️ Real API Call)

**Note**: This uses the **free tier** - zero cost!

```python
from civic_chat_router import ChatRouter

# Create router
router = ChatRouter()

# Test query planning (should use free Gemini if available)
result = router.route_message(
    message="show housing meetings in Berkeley",
    conversation_history=[],
    context={},
    mode="navigation",
    serialized_context={}
)

print("Action:", result.get('action'))
print("Parameters:", result.get('parameters', {}))
```

**Expected output**: Should successfully parse the query and return search parameters.

---

## Verification Checklist

After testing, verify:

- [ ] **Provider instantiation works** (Test 1 passes)
- [ ] **5 OpenRouter models in registry** (Test 2 shows all models)
- [ ] **Task routing includes OpenRouter** (Test 3 shows OpenRouter models in config)
- [ ] **Model selection works** (Test 4 picks correct models)
- [ ] **Free tier completion works** (Test 5 returns response, $0 cost)
- [ ] **Chat routing works** (Test 6 parses query successfully)
- [ ] **Cost savings verified** (Test 7 shows 73% savings potential)

---

## Cost Monitoring

### Check OpenRouter Dashboard

1. Go to https://openrouter.ai/activity
2. View recent API calls
3. Check costs (should be $0 if using free tier)
4. Monitor usage limits

### Expected Costs

**During testing** (with free tier):
- Simple completion test: **$0** (free tier)
- Chat routing test: **$0** (free tier)
- Total testing cost: **$0**

**Production usage** (100 users, 100 queries/month):
- With OpenRouter optimization: **$0.48-0.72/month** (73% savings)
- With free tier only: **$0/month** (100% savings during development)

---

## Troubleshooting

### Error: "OPENROUTER_API_KEY not set"

**Solution**:
```bash
export OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY-HERE"
```

### Error: "Authentication failed"

**Possible causes**:
1. API key incorrect → Check https://openrouter.ai/keys
2. API key expired → Generate new key
3. Account issue → Check OpenRouter dashboard

### Error: "Model not available"

**Solution**: OpenRouter model might be temporarily unavailable. The system will automatically fall back to the next model in priority list.

### Free tier not working

**Check**:
1. Using exact model name: `google/gemini-2.0-flash-exp:free`
2. Free tier has rate limits (check OpenRouter dashboard)
3. May need to add billing method even for free tier (OpenRouter requirement)

---

## Advanced Testing Scenarios

### Test 1: Cost Optimization

Compare costs across models:

```python
from model_registry import get_model_info

models = [
    'gpt-4o-mini',                           # OpenAI direct: $0.60/1M
    'openai/gpt-4o-mini',                    # OpenRouter: $0.15/1M
    'meta-llama/llama-3.3-70b-instruct',     # OpenRouter: $0.59/1M
    'google/gemini-2.0-flash-exp:free',      # OpenRouter: $0.00/1M
]

for model in models:
    info = get_model_info(model)
    cost = info['cost_per_1m_tokens']
    print(f"{model:45s} ${cost:.2f}/1M")
```

### Test 2: Fallback Behavior

Test what happens when OpenRouter is unavailable:

```python
# Temporarily unset OpenRouter key
import os
openrouter_key = os.getenv('OPENROUTER_API_KEY')
del os.environ['OPENROUTER_API_KEY']

from llm_provider import get_model_for_task

# Should fall back to non-OpenRouter models
provider = get_model_for_task('navigation')
print("Fallback model:", provider.default_model)  # Should be gpt-4o-mini

# Restore key
os.environ['OPENROUTER_API_KEY'] = openrouter_key
```

### Test 3: Multiple Models

Test different OpenRouter models:

```python
from llm_provider import get_model

models_to_test = [
    'meta-llama/llama-3.3-70b-instruct',      # Fast & cheap
    'anthropic/claude-3-5-haiku',             # Quality & affordable
    'google/gemini-2.0-flash-exp:free',       # Free tier
]

for model_name in models_to_test:
    provider = get_model(model_name)
    print(f"\nTesting {model_name}:")
    print(f"  Provider: {provider.name}")
    print(f"  Model: {provider.default_model}")

    # Optionally make API call (commented out to avoid costs)
    # result = provider.complete([{"role": "user", "content": "Hi!"}])
    # print(f"  Response: {result.content[:50]}...")
```

---

## Next Steps

After successful testing:

1. **Verify cost savings**: Check OpenRouter dashboard for actual usage
2. **Update environment**: Add `OPENROUTER_API_KEY` to `.env` file
3. **Production testing**: Test with real civic chat queries
4. **Monitor performance**: Compare response quality across models
5. **Consider merge**: If all tests pass, ready to merge feature branch

---

## Questions?

**Documentation**:
- Full architecture: `docs/core/LLM_PROVIDER_ARCHITECTURE.md`
- Model registry: `src/model_registry.py`
- Provider implementation: `src/providers/openai_compatible_provider.py`

**OpenRouter Resources**:
- Dashboard: https://openrouter.ai/
- Models: https://openrouter.ai/models
- Docs: https://openrouter.ai/docs
- Pricing: https://openrouter.ai/models (per-model pricing)

**Support**:
- OpenRouter Discord: https://discord.gg/openrouter
- Civic project: `docs/core/next_session_prompt.md`
