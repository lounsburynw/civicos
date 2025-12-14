# LLM Provider Status

Current status of all LLM providers in the Civic Conversational OS platform.

**Last Updated:** 2025-11-06 (Session 70)

---

## Production-Ready Providers

### ✅ OpenAI
- **Status:** Production
- **Primary Model:** gpt-4o-mini
- **Use Cases:**
  - Conversational queries (focus/compare modes)
  - Function calling (structured actions)
  - Comment drafting
- **Cost:** ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens
- **Configuration:** `OPENAI_API_KEY` environment variable

### ✅ Google Gemini
- **Status:** Production
- **Primary Model:** gemini-2.0-flash-exp
- **Use Cases:**
  - Navigation queries (search/filter operations)
  - Mode detection
  - Structured outputs (JSON schema)
- **Cost:** ~$0.01875 per 1M input tokens (85% cheaper than OpenAI)
- **Configuration:** `GOOGLE_API_KEY` environment variable
- **Notes:**
  - Schema normalization implemented for structured outputs
  - Converts OpenAI-style json_schema to Gemini format
  - Removes unsupported fields (additionalProperties, array types)

### ✅ Anthropic Claude
- **Status:** Production-ready (enabled)
- **Primary Model:** claude-sonnet-4-20250514
- **Use Cases:**
  - Research queries (quality fallback after Gemini)
  - Long document analysis (200K context)
  - Conversational queries (reasoning fallback after OpenAI)
- **Cost:** ~$3 per 1M input tokens (5x OpenAI, high quality)
- **Configuration:**
  - `ANTHROPIC_API_KEY` environment variable
  - `ENABLE_ANTHROPIC=true` feature flag (enabled)
- **Notes:**
  - 200K context window (vs Gemini Pro's 2M)
  - Superior reasoning for complex civic policy questions
  - Used as quality fallback, not cost optimization

---

## Experimental Providers

### ⚠️ Groq
- **Status:** Experimental (untested in production)
- **Primary Model:** llama-3.1-70b-versatile
- **Use Cases:** Fast inference (low latency)
- **Cost:** Free tier available
- **Configuration:** `GROQ_API_KEY` environment variable
- **Notes:** Provider code exists but not validated with civic platform

### ⚠️ Perplexity
- **Status:** Experimental (untested in production)
- **Primary Model:** llama-3.1-sonar-large-128k-online
- **Use Cases:** Research queries with real-time data
- **Cost:** ~$1 per 1M tokens
- **Configuration:** `PERPLEXITY_API_KEY` environment variable
- **Notes:** Intended for future research mode (Phase 2)

---

## Smart Routing

The platform uses intelligent provider routing based on task type:

| Task Type | Provider | Model | Cost Savings |
|-----------|----------|-------|--------------|
| Navigation queries | Gemini | flash-exp | 85% vs OpenAI |
| Mode detection | Gemini | flash-exp | 85% vs OpenAI |
| Conversational | OpenAI/Claude | gpt-4o-mini/sonnet-4 | Quality priority |
| Research | Gemini/Claude | flash-exp/sonnet-4 | Balanced |
| Long documents | Gemini Pro/Claude | pro-1.5/sonnet-4 | Context priority |
| Comment drafting | OpenAI | gpt-4o-mini | N/A (quality) |

**Total Cost Reduction:** ~70% overall with smart routing

---

## Validation

Run the provider validation script to check your configuration:

```bash
python scripts/validate_providers.py
```

This will show:
- Which providers are configured (API keys present)
- Which providers are production-ready
- Current default provider
- Smart routing status

---

## Adding New Providers

To add a new provider:

1. Create provider class in `src/providers/` that implements `LLMProvider` interface
2. Add provider to `src/llm_provider.py` factory
3. Add task routing logic to `get_provider_for_task()` if needed
4. Test with validation script
5. Update this documentation

See `src/providers/base.py` for the required interface.

---

## Known Limitations

- **Gemini:** Doesn't support nullable array types `["string", "null"]` in JSON schema
  - Solution: Schema normalization converts to single types
- **Anthropic:** Requires feature flag to enable (enabled in production)
  - Reason: Uses lazy import to avoid requiring SDK dependency when not used
- **Groq/Perplexity:** Not tested in production environment
  - Status: Provider code exists, but needs validation

---

## Future Roadmap

1. **Research Mode (Phase 2):** Perplexity for real-time civic data queries
2. **Cost Dashboard:** Track per-provider usage and costs
3. **Automatic Fallback:** Retry with different provider on failure
4. **Additional Providers:** Groq for fast inference (experimental)
