# Bug: Mission Execution Fails with Unknown Error

**Environment:**
- OS: Windows 10
- Spark bundle: telegram-starter
- LLM: Anthropic Claude (sonnet, claude_oauth)
- Node: v25.8.0
- Date: 2026-05-23

**Steps to Reproduce:**
1. Install Spark with Anthropic Claude provider on Windows
2. Connect Telegram bot via telegram-starter bundle
3. Send `/run say exactly OK` in Telegram

**Expected:** Mission completes and bot replies "OK"

**Actual:** 
- Bot acknowledges: "I will run that through Claude now"
- Then returns: "That run hit a blocker. spark-run could not finish this step. unknown error"

**Logs:**

Clarification microcopy LLM failed: ERR_BAD_REQUEST
LLM: OFFLINE
WARNING: LLM provider is not reachable. Natural language disabled.

**Notes:**
- Chat and planning work correctly
- Build execution fails consistently
- Reproducible on every `/run` command
