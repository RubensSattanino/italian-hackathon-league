# Italian Hackathon League – Brambilla CRM

A CRM built from scratch at the final of the **Italian Hackathon League** (The Final Hackathon, October 9, 2026, OGR Turin).

Its first client is Brambilla Forniture S.p.A. The CRM imports 15 years of data from the legacy Sinergia 4 system, exposes an **API compatible with HubSpot CRM**, and includes an **AI chat assistant** that works on the data.

## Features
- **HubSpot-compatible API** (`/crm/v3`, `/crm/v4` and the versioned `/crm/{module}/2026-09` paths): objects, search, associations, properties, pipelines, owners, lists, import/export, and HubSpot-style errors.
- **Migration** (`POST /__migrate`): normalizes and deduplicates companies, contacts, deals, the price list, quote lines, tickets and activities (R1–R6).
- **Business rules**:
  - unique VAT number, with a 409 on duplicates (R7);
  - 2025 revenue and A/B/C customer class (R8);
  - "Clienti dormienti" (dormant customers) list (R9);
  - supply kickoff ticket when a deal is won (R10);
  - follow-up call task when a deal is lost (R11);
  - automatic contact-to-company association from the email domain (R12).
- **Assistant** (`POST /__agente`): `openai/gpt-6-luna` via OpenRouter, with tool calling on the CRM (R13).
- **Web interface**: companies, contacts, deals board, tickets, dormant customers, price list and assistant.

## Stack
Python, Starlette, SQLite (on a Railway volume mounted at `/data`). Deployed on Railway.

## Environment variables
- `CRM_TOKEN`: the API Bearer token.
- `OPENROUTER_API_KEY`: the key for the assistant's model.
- `DATA_DIR` (optional, defaults to `/data`).
