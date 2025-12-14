# Frontend Testing Guide - OpenRouter Models

**Testing Kimi K2 Thinking & DeepSeek R1 in the Civic Workspace**

This guide shows how to test the new OpenRouter models (Moonshot Kimi K2, DeepSeek R1, DeepSeek Chat) interactively in the frontend.

---

## Quick Start - Backend API Testing

First, test the models via the backend API to verify they work:

```bash
# From project root
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

# Test the new models interactively
python scripts/test_openrouter_models.py
```

This will let you:
- Test Kimi K2 Thinking ($2.00/1M)
- Test DeepSeek R1 ($0.55/1M)
- Test DeepSeek Chat ($0.27/1M)
- Test free Gemini tier ($0/1M)
- Use custom prompts
- See token usage and costs

---

## Frontend Integration Testing

### Step 1: Start the Backend Servers

Open **3 terminal windows**:

#### Terminal 1: Backend REST API
```bash
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

# Ensure .env has OPENROUTER_API_KEY
source .env

# Start API server (port 8001)
python src/civic_api_integrated.py
```

**Expected output**: `Running on http://127.0.0.1:8001`

#### Terminal 2: WebSocket Server (Optional - for real-time features)
```bash
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

# Start WebSocket server (port 8002)
python src/civic_socketio_server.py
```

**Expected output**: `Server initialized for SocketIO`

#### Terminal 3: Frontend Dev Server
```bash
cd /Users/nicolaslounsbury/projects/civic/frontend/civic-workspace

# Start Vite dev server (port 5173)
npm run dev
```

**Expected output**: `Local: http://localhost:5173/`

### Step 2: Open the Frontend

Open your browser to: **http://localhost:5173/**

You should see the Civic Workspace interface.

---

## Testing the New Models

### Current Behavior (Automatic Model Selection)

The chat routing system will **automatically select models** based on the task:

**Conversational queries** → Will try models in this priority:
1. `anthropic/claude-3.5-sonnet` (if OPENROUTER_API_KEY set)
2. `claude-sonnet-4` (if ANTHROPIC_API_KEY set)
3. **`moonshotai/kimi-k2-thinking`** ← NEW! (if others fail)
4. **`deepseek/deepseek-r1`** ← NEW! (if others fail)
5. **`deepseek/deepseek-chat`** ← NEW! (if others fail)
6. Fallback to other providers

### Test Queries in the Frontend

Try these queries in the chat interface:

#### Test 1: Simple Search (tests model routing)
```
show housing meetings in Berkeley
```

**What to observe**:
- Chat should route to appropriate model
- Should return search results
- Check browser console for which model was used

#### Test 2: Complex Reasoning (may use thinking models)
```
Explain the relationship between CDBG funding and local housing policy
```

**What to observe**:
- More complex query may trigger different model selection
- Response quality/depth
- Token usage (check backend logs)

#### Test 3: Multi-step Query
```
Find housing meetings in Berkeley, then explain what CDBG funding is
```

**What to observe**:
- Function calling behavior
- Model handles multi-part query
- Response coherence

---

## Forcing Specific Model Testing

To test a **specific model** (like Kimi K2 or DeepSeek R1), you have two options:

### Option A: Modify Task Priority (Temporary)

Edit `src/llm_provider.py` and change the conversational task priority:

```python
'conversational': {
    'strategy': 'explicit',
    'model_priority': [
        'moonshotai/kimi-k2-thinking',  # Move to top for testing!
        # ... other models
    ],
    # ...
}
```

Then restart the backend server.

### Option B: Use the Backend Test Script

Test models directly via API (bypasses frontend):

```bash
python scripts/test_openrouter_models.py
```

Select the model you want to test and enter your prompt.

### Option C: Create a Custom Chat Endpoint

Add a test endpoint to `civic_api_integrated.py`:

```python
@app.post("/api/chat/test-model")
def test_specific_model(request: dict):
    """Test a specific model by name."""
    model_name = request.get('model', 'gpt-4o-mini')
    message = request.get('message', 'Hello')

    from llm_provider import get_model
    provider = get_model(model_name)

    result = provider.complete([
        {"role": "user", "content": message}
    ])

    return {
        "model": model_name,
        "response": result.content,
        "usage": result.usage
    }
```

Then call it from frontend or curl:

```bash
curl -X POST http://localhost:8001/api/chat/test-model \
  -H "Content-Type: application/json" \
  -d '{
    "model": "moonshotai/kimi-k2-thinking",
    "message": "Explain civic engagement in 2 sentences"
  }'
```

---

## Monitoring Model Usage

### Backend Logs

Watch the backend terminal for model selection:

```
ChatRouter initialized with claude-sonnet-4-20250514
```

or

```
Using model: moonshotai/kimi-k2-thinking
```

### Browser Console

Open browser DevTools (F12) → Console tab

Look for chat routing logs showing which model was used.

### OpenRouter Dashboard

Check real-time usage at: **https://openrouter.ai/activity**

You'll see:
- Which models were called
- Token usage
- Actual costs
- Response times

---

## Cost Monitoring

**New models costs**:
- Kimi K2 Thinking: **$2.00/1M tokens**
- DeepSeek R1: **$0.55/1M tokens**
- DeepSeek Chat: **$0.27/1M tokens**

**Typical query** (1000 input + 200 output = 1200 tokens):
- Kimi K2: ~$0.0024 per query
- DeepSeek R1: ~$0.00066 per query
- DeepSeek Chat: ~$0.00032 per query
- Free Gemini: **$0** per query

**100 queries for testing**:
- Kimi K2: ~$0.24
- DeepSeek R1: ~$0.07
- DeepSeek Chat: ~$0.03

---

## Testing Checklist

- [ ] Backend API server running (port 8001)
- [ ] Frontend dev server running (port 5173)
- [ ] OPENROUTER_API_KEY configured in .env
- [ ] Browser open to http://localhost:5173/
- [ ] Can send chat messages
- [ ] Models responding correctly
- [ ] Token usage visible in logs
- [ ] OpenRouter dashboard shows activity

---

## Troubleshooting

### Error: "OPENROUTER_API_KEY not set"

**Solution**: Check .env file has the key:
```bash
grep OPENROUTER_API_KEY .env
```

If not, add it:
```bash
echo 'OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY"' >> .env
```

### Error: "Model not available"

**Possible causes**:
1. Model name typo (check `src/model_registry.py`)
2. Model temporarily unavailable on OpenRouter
3. API key not configured

**Solution**: Check available models:
```python
from model_registry import get_models_by_provider
print(get_models_by_provider('openrouter'))
```

### Frontend not connecting to backend

**Check**:
1. Backend running on port 8001? `lsof -i :8001`
2. Correct API URL in frontend? (should be `http://localhost:8001`)
3. CORS enabled? (should be automatic)

### Model selection not working

**Debug**:
1. Check `src/llm_provider.py` task priority order
2. Verify model is in `model_registry.py`
3. Check backend logs for model selection
4. Test with backend script first: `python scripts/test_openrouter_models.py`

---

## Advanced: A/B Testing Models

To compare model responses, create test queries:

**Test query**: "Explain how community development block grants work"

**Test with different models**:
1. Default (whatever is selected)
2. Force Kimi K2 (modify priority)
3. Force DeepSeek R1 (modify priority)
4. Force DeepSeek Chat (modify priority)

**Compare**:
- Response quality
- Response length
- Token usage
- Cost
- Response time

---

## Next Steps

After testing:

1. **Evaluate model quality** - Which gives best civic responses?
2. **Check costs** - OpenRouter dashboard shows actual spend
3. **Update priorities** - Adjust `TASK_MODEL_CONFIG` based on results
4. **Document findings** - Note which models work best for civic queries
5. **Consider defaults** - Should Kimi K2 or DeepSeek be default for certain tasks?

---

## Quick Reference

**Start everything**:
```bash
# Terminal 1: Backend
cd /Users/nicolaslounsbury/projects/civic && source civic-env/bin/activate && python src/civic_api_integrated.py

# Terminal 2: Frontend
cd /Users/nicolaslounsbury/projects/civic/frontend/civic-workspace && npm run dev
```

**Test models directly**:
```bash
python scripts/test_openrouter_models.py
```

**Check OpenRouter usage**:
https://openrouter.ai/activity

**Model registry location**:
`src/model_registry.py` lines 132-155

**Task routing config**:
`src/llm_provider.py` lines 244-259

---

Ready to test! 🚀
