# Italian Hackathon League – Brambilla CRM

CRM costruito da zero durante la finale dell'**Italian Hackathon League** (The Final Hackathon, 9 ottobre 2026, OGR Torino).

Il primo cliente è Brambilla Forniture S.p.A.: il CRM importa i 15 anni di dati del vecchio Sinergia 4, espone un'**API compatibile con HubSpot CRM** e ha un **assistente AI in chat** che lavora sui dati.

## Cosa fa
- **API compatibile HubSpot** (`/crm/v3`, `/crm/v4`): oggetti, ricerca, associazioni, proprietà, pipeline, owner, liste, import/export, errori in formato HubSpot.
- **Migrazione** (`POST /__migrate`): normalizza e deduplica aziende, contatti, trattative, listino, righe d'offerta, ticket e attività (R1–R6).
- **Regole**:
  - P.IVA unica, con 409 sui duplicati (R7);
  - fatturato 2025 e classe A/B/C (R8);
  - lista dei Clienti dormienti (R9);
  - ticket "Avvio fornitura" quando una trattativa è vinta (R10);
  - task "Richiamare" quando è persa (R11);
  - associazione del contatto all'azienda dal dominio dell'email (R12).
- **Assistente** (`POST /__agente`): `openai/gpt-6-luna` via OpenRouter con tool calling sul CRM (R13).
- **Interfaccia web** in inglese: aziende, contatti, board delle trattative, ticket, clienti dormienti, listino, assistente.

## Stack
Python, Starlette, SQLite (su un volume Railway in `/data`). Deploy su Railway.

## Variabili d'ambiente
- `CRM_TOKEN`: il token Bearer delle API.
- `OPENROUTER_API_KEY`: la chiave del modello dell'assistente.
- `DATA_DIR` (opzionale, default `/data`).
