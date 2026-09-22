# AI Chatbot for ERPNext

A read-only, permission-aware chatbot inside the ERPNext Desk. Ask in **English, French or Arabic**:
"Show me today's sales", "Combien de clients avons-nous ?", "ما هي الفواتير غير المدفوعة؟", "Show the stock status"...
Answers come back as short summaries, stat cards and tables (with links to documents and CSV download).

Compatible with Frappe / ERPNext **v15** (v16 should work; see notes).

## Install

```bash
cd ~/frappe-bench
# from git
bench get-app https://github.com/<you>/ai_chatbot.git
# or from this folder (must be a git repo):  cd ai_chatbot && git init && git add . && git commit -m init
#   bench get-app /path/to/ai_chatbot

bench --site yoursite.local install-app ai_chatbot
bench --site yoursite.local migrate
bench build --app ai_chatbot
bench restart            # production: sudo supervisorctl restart all
```

An **AI Chatbot** item appears in the sidebar and on the Apps screen; it opens `/app/ai-chat`.
Uninstall: `bench --site yoursite.local uninstall-app ai_chatbot`.

## Configure (System Manager) — search "AI Chatbot Settings"

| Setting | Meaning |
|---|---|
| Queryable DocTypes | Allow-list, one per line. Nothing outside it is ever queried. |
| Provider | *Built-in* (default, offline rules, no data leaves your server) or *Anthropic* / *OpenAI-compatible* (LLM plans the query for free-form questions). |
| Let the AI write the final answer | Off by default. When on, result rows (already permission-filtered) are sent to the provider. |
| Max rows / rate limit | Caps per answer and per user per minute. |
| Audit log | Every question, executed plan, status and duration is stored in **AI Chatbot Log** (auto-purged). |

Anthropic example: Provider `Anthropic`, Model `claude-sonnet-5`, paste the API key.
OpenAI-compatible: set Base URL (e.g. a self-hosted Ollama/vLLM endpoint `http://host:11434/v1`), Model, API key.
If the LLM is unreachable or returns an invalid plan the built-in engine answers instead.

## How security works

1. **Session user only.** Endpoints are `@frappe.whitelist(methods=["POST"/"GET"])`, System Users only; CSRF protected by Frappe.
2. **No SQL from the bot.** The engine (LLM or rules) can only emit a *plan* made of 3 read-only tools (`count`, `list`, `aggregate`).
   Plans are validated (DocType allow-list + hard block-list, field names checked against DocType meta, operator/value whitelist,
   max 4 steps, max 8 filters) and executed with `frappe.get_list`, which enforces **role permissions, user permissions,
   document sharing and field-level (permlevel) access** for the current user.
3. **Read-only by construction.** No code path inserts, updates, submits, cancels or deletes business documents
   (the only write is the app's own audit log entry).
4. Sensitive fields (password/secret/token/api_key...), Password/Attach/Code fields, and system DocTypes
   (User, Role, DocPerm, Error Log, OAuth*, Settings...) are never exposed.
5. Rate limiting, DB statement timeout (MariaDB `max_statement_time`), row caps, input length cap, XSS-safe rendering.
6. Prompt injection: the LLM has no tools besides producing a plan that is re-validated server-side.

Privacy note: in LLM mode the question and the *schema* (DocType/field names the user may read) are sent to the provider.
Row data is sent only if "Let the AI write the final answer" is enabled.

## Structure

```
ai_chatbot/
├─ pyproject.toml · README.md · license.txt
└─ ai_chatbot/
   ├─ hooks.py · install.py (sidebar Workspace) · tasks.py (log purge) · api.py (endpoints)
   ├─ services/  security.py · query_engine.py · intents.py · llm.py · chatbot.py · messages.py
   ├─ ai_chatbot/           (module)
   │  ├─ doctype/ai_chatbot_settings · ai_chatbot_log
   │  └─ page/ai_chat/      (chat UI: ai_chat.js)
   ├─ public/  css/ai_chatbot.css · js/ai_chatbot_boot.js · images/
   ├─ translations/ ar.csv · fr.csv
   └─ tests/
```

## API

`POST /api/method/ai_chatbot.api.chat` `{message, history?}` →
`{ok, reply, blocks:[{type:"stats"|"table",...}], lang, mode}`; `GET /api/method/ai_chatbot.api.get_config`.

## Extending

* New question types: add keywords/plans in `services/intents.py` (or just enable an LLM provider).
* More data: add DocTypes to *Queryable DocTypes*. Amount sums use `base_grand_total` (company currency).
* Tests: `bench --site yoursite.local run-tests --app ai_chatbot`.

## Notes / limits

* Child tables and Single DocTypes are intentionally not queryable.
* Unpaid totals sum `outstanding_amount` in each invoice's own currency.
* Chat history is stored in the browser (localStorage, per user); "New chat" clears it.
* v16: the sidebar entry is a Workspace redirected to the page by `ai_chatbot_boot.js`; if your v16 build
  changes workspace routes, the Apps-screen tile and `/app/ai-chat` still work.
# erpnext_bot_ai
