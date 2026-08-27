# Bug: Spawner Build Execution Fails on All LLM Providers

**Environment:**
- OS: Windows 10
- Spark bundle: telegram-starter
- Node: v25.8.0
- Date: 2026-05-25

**Steps to Reproduce:**
1. Install Spark with any LLM provider
2. Send `/run say exactly OK` in Telegram
3. Spark acknowledges and plans but execution fails

**Tested Providers:**
- Anthropic Claude (sonnet, claude_oauth) → FAILS
- OpenAI via FreeModel (gpt-5.5, api_key) → FAILS

**Expected:** Mission completes and replies "OK"

**Actual:** "spark-run could not finish this step. unknown error"

**Logs:**
- PRDBridge Auto-analysis (openai): not-started
- Clarification microcopy LLM failed: ERR_BAD_REQUEST

**Notes:**
- Chat works on all providers
- Planning works on all providers
- Build execution fails consistently on ALL providers
- This is a Spawner-level bug not related to LLM provider
