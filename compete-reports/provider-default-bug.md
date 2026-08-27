# Bug: spark setup defaults to OpenAI despite choosing different provider

**Reported by:** Team Syntax Layer
**Date:** 2026-05-24

## What happened
After completing spark setup and selecting different providers 
(OpenRouter, Anthropic API key, and Anthropic Claude sign-in),
spark providers status always shows provider=openai model=gpt-5.5. 
No provider selection persists across multiple attempts.

## Repro steps
1. Run ~/.spark/bin/spark setup telegram-starter
2. Select option 3 (Use an API key) then option 3 (OpenRouter)
3. Complete setup with valid OpenRouter API key
4. Run ~/.spark/bin/spark providers status
5. All roles show provider=openai model=gpt-5.5 — wrong provider
6. Re-run ~/.spark/bin/spark setup telegram-starter
7. Select option 2 (Use my Claude sign-in)
8. Complete setup successfully
9. Run ~/.spark/bin/spark providers status again
10. All roles still show provider=openai model=gpt-5.5

## Expected behavior
The provider selected during spark setup should be saved and 
reflected in spark providers status for all four roles.
Selecting OpenRouter should show provider=openrouter.
Selecting Claude sign-in should show provider=anthropic auth=claude_oauth.

## Before proof
spark providers status showed provider=openai model=gpt-5.5
after trying OpenRouter, Anthropic API key, and Claude sign-in.
All three attempts reverted to OpenAI.

## After fix
spark providers status should reflect whichever provider the 
user selected during setup, not default back to OpenAI.
