# Cloud Kitchen WhatsApp AI Agent

A production-grade, AI-powered WhatsApp assistant for a food delivery business.
Built with Python, FastAPI, Google Gemini, and Google Sheets.

---

## What This Does

Customers message your business on WhatsApp and receive intelligent, natural responses:

- 🍽️ **Menu browsing** — reads live inventory from Google Sheets
- ❓ **FAQ answers** — reads from your FAQ sheet
- 🛒 **Order taking** — collects items, quantity, address, and payment method
- ✅ **Order confirmation** — writes confirmed orders to Google Sheets *only after validation*
- 🚫 **Safety** — never invents prices, never confirms orders the AI didn't actually save

---

## Architecture

```
WhatsApp (Meta Cloud API)
    │
    ▼
POST /webhook  ──►  Background Task
                         │
                         ▼
                   AIService (Gemini)
                    ├─ InventoryService ──► Google Sheets (Inventory)
                    ├─ FAQService ──────► Google Sheets (FAQs)
                    └─ OrderService ───► Google Sheets (Orders)
                         │
                         ▼
                   WhatsAppClient ──► Customer reply
```

### Module Map

| Module | File(s) | Responsibility |
|--------|---------|----------------|
| Config | `src/app/config.py` | Typed env var loading |
| Logging | `src/app/logging_config.py` | Structured JSON logs with redaction |
| Webhook | `src/app/api/webhook.py` | Meta verification + receive messages |
| WhatsApp Client | `src/app/integrations/whatsapp_client.py` | Send outbound messages |
| Sheets Client | `src/app/integrations/sheets_client.py` | Google Sheets read/write |
| Inventory Service | `src/app/services/inventory_service.py` | Menu lookup, availability |
| FAQ Service | `src/app/services/faq_service.py` | FAQ search |
| Order Service | `src/app/services/order_service.py` | Validation + order persistence |
| AI Service | `src/app/services/ai_service.py` | Gemini conversation management |
| Conversation State | `src/app/services/conversation_state.py` | Per-customer chat history |
| Message Processor | `src/app/services/message_processor.py` | Routes messages to AI |
| Idempotency | `src/app/utils/idempotency.py` | Deduplicates webhook events |

---

## Prerequisites

- Python 3.10 or newer
- A Google Cloud service account with access to your Sheets
- A Meta WhatsApp Business Platform account with a test phone number
- A Google Gemini API key (get one free at [aistudio.google.com](https://aistudio.google.com))

---

## Quick Start (After Every Computer Restart)

```powershell
# 1. Navigate to the project folder
cd "d:\BlackVein_Projects\Automations\Whatsapp Automation projects\Cloud Kitchen"

# 2. Activate the virtual environment
.\venv\Scripts\Activate.ps1

# 3. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. (Optional) Open a public HTTPS tunnel for webhook testing
# In a SECOND terminal:
.\venv\Scripts\Activate.ps1
ngrok http 8000
```

The app runs at: http://localhost:8000
API docs: http://localhost:8000/docs

---

## Installation (First Time Only)

```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Copy and fill in your credentials
copy .env.example .env
# Edit .env with your real values (see Configuration section below)
```

---

## Configuration

Copy `.env.example` to `.env` and fill in these values:

### Required for WhatsApp

| Variable | Where to find it |
|----------|-----------------|
| `WHATSAPP_ACCESS_TOKEN` | Meta Developer Portal → Your App → WhatsApp → API Setup |
| `WHATSAPP_PHONE_NUMBER_ID` | Same page — "Phone Number ID" (NOT the business account ID) |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Make up any random string — you'll enter it in Meta portal too |

### Required for Google Sheets

| Variable | How to get it |
|----------|---------------|
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | Download from Google Cloud Console → IAM → Service Accounts → Keys → Add Key → JSON. Save as `credentials/service_account.json` |
| `INVENTORY_SPREADSHEET_ID` | The long ID in your Google Sheet URL: `docs.google.com/spreadsheets/d/THIS_PART/edit` |
| `FAQ_SPREADSHEET_ID` | Same — for your FAQ sheet |
| `ORDERS_SPREADSHEET_ID` | Same — for your Orders sheet |
| `INVENTORY_WORKSHEET_NAME` | The tab name (e.g. `Inventory`) |
| `FAQ_WORKSHEET_NAME` | The tab name (e.g. `faqs`) |
| `ORDERS_WORKSHEET_NAME` | The tab name (e.g. `Orders`) |

**Important:** Share each Google Sheet with your service account's email address (from the JSON file) with **Editor** access.

### Required for AI

| Variable | How to get it |
|----------|---------------|
| `LLM_PROVIDER` | Set to `google` |
| `LLM_API_KEY` | Get a free key at [aistudio.google.com](https://aistudio.google.com) |
| `LLM_MODEL` | `gemini-1.5-flash` (fast and free-tier friendly) |

---

## Data Files

The `data/` directory contains your spreadsheet export (`Food_Delivery_System.xlsx`).

**This is a local snapshot only.** Changes here do NOT update the online Google Sheet.

The live automation reads from and writes to the online sheets configured in `.env`.

### Spreadsheet Schema

**Inventory sheet** (`Inventory` tab):
| Column | Type | Notes |
|--------|------|-------|
| item_id | string | e.g. I001 |
| item_name | string | Shown to customers |
| description | string | Shown to customers |
| category | string | Used for menu grouping |
| price | number | In Indian Rupees (₹) |
| available | Yes/No | Controls if item can be ordered |
| quantity | number | Stock count |

**Orders sheet** (`Orders` tab):
| Column | Type | Notes |
|--------|------|-------|
| order_id | string | Auto-generated (ORD-YYYYMMDDHHMMSS-XXXX) |
| customer_name | string | From WhatsApp profile |
| phone | string | Customer's WhatsApp number |
| item_name | string | Comma-joined for multi-item orders |
| quantity | string | Comma-joined quantities |
| unit_price | string | Comma-joined prices |
| total_amount | number | Sum calculated in Python (never AI) |
| delivery_address | string | Collected during conversation |
| payment_method | string | UPI / Cash on Delivery / Card |
| order_status | string | Pending (default) |
| order_date | string | UTC timestamp |

**FAQ sheet** (`faqs` tab):
| Column | Notes |
|--------|-------|
| faq_id | e.g. FAQ001 |
| question | Shown to match against customer queries |
| keywords | Comma-separated keywords for matching |
| answer | Sent to the AI as reference |
| category | Grouping only |
| active | Yes = included, No = skipped |

---

## Running Tests

```powershell
# All tests (115 tests, no external API calls)
venv\Scripts\python.exe -m pytest tests/ -v

# Just Module 3 (Sheets + Business Logic)
venv\Scripts\python.exe -m pytest tests/test_sheets_integration.py -v

# Just Module 4 (AI Service)
venv\Scripts\python.exe -m pytest tests/test_ai_service.py -v

# Just Module 5 (End-to-End)
venv\Scripts\python.exe -m pytest tests/test_end_to_end.py -v
```

---

## Webhook Setup (Meta Developer Portal)

1. Start your server and expose it with ngrok: `ngrok http 8000`
2. Copy the ngrok HTTPS URL (e.g. `https://abc123.ngrok.io`)
3. In Meta Developer Portal → Your App → WhatsApp → Configuration:
   - **Webhook URL**: `https://abc123.ngrok.io/webhook`
   - **Verify Token**: The same value as `WHATSAPP_WEBHOOK_VERIFY_TOKEN` in your `.env`
4. Click **Verify and Save**
5. Subscribe to the `messages` webhook field

**Note:** The ngrok URL changes every time you restart it unless you use a paid plan.
For production, use a fixed domain and a real HTTPS certificate.

---

## Deployment Considerations

- **Process manager**: Use `supervisord` or `systemd` to keep uvicorn running
- **HTTPS**: Terminate SSL at nginx or a load balancer — never expose HTTP to Meta
- **Conversation state**: Currently in-memory. For multi-server or restart-safe deployment, replace `ConversationStore` with a Redis backend
- **Secrets**: Use environment variables or a secrets manager (AWS Secrets Manager, GCP Secret Manager). Never commit `.env` or the service account JSON
- **Rate limits**: Google Sheets API has a quota of 300 requests per minute per project. The inventory cache (5-minute TTL) reduces sheet reads significantly
- **Google Sheets for Orders**: If order volume is high, consider migrating to a proper database (PostgreSQL, Firestore). Sheets works well up to a few hundred orders per day

---

## Security Notes

- `.env` is in `.gitignore` — it will never be committed
- `credentials/` is in `.gitignore` — service account keys are excluded
- Phone numbers are masked in all log output (`9191****`)
- Access tokens are never printed in logs
- Customer messages are never stored beyond the in-memory conversation buffer
- The AI cannot access raw credentials or internal system prompts from the customer side

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| `Module 3 missing config vars` at startup | Fill in Google Sheets vars in `.env` |
| `SpreadsheetNotFound` | Check `INVENTORY_SPREADSHEET_ID` and share the sheet with your service account email |
| `WorksheetNotFound` | The tab name doesn't match. Check `INVENTORY_WORKSHEET_NAME` in `.env` |
| `401 Unauthorized` from WhatsApp API | `WHATSAPP_ACCESS_TOKEN` expired. Regenerate it in Meta Developer Portal |
| Webhook verification fails (403) | `WHATSAPP_WEBHOOK_VERIFY_TOKEN` in `.env` doesn't match what you entered in Meta portal |
| AI always says "temporarily unavailable" | Check `LLM_API_KEY` in `.env` and that `LLM_PROVIDER=google` |
| Ngrok tunnel not working | Make sure the server is running on port 8000 before starting ngrok |

---

## Project File Tree

```
Cloud Kitchen/
├── src/app/
│   ├── main.py                          # FastAPI entry point
│   ├── config.py                        # Typed config from env vars
│   ├── logging_config.py                # Structured logging + redaction
│   ├── api/
│   │   ├── health.py                    # GET /health
│   │   └── webhook.py                   # GET+POST /webhook
│   ├── integrations/
│   │   ├── whatsapp_client.py           # Send WhatsApp messages
│   │   └── sheets_client.py             # Google Sheets read/write
│   ├── services/
│   │   ├── message_processor.py         # Route messages to AI
│   │   ├── ai_service.py                # Gemini conversation + order detection
│   │   ├── conversation_state.py        # Per-customer chat history
│   │   ├── inventory_service.py         # Menu lookup + availability
│   │   ├── faq_service.py               # FAQ matching
│   │   └── order_service.py             # Validate + persist orders
│   ├── models/
│   │   ├── whatsapp.py                  # WhatsApp webhook Pydantic models
│   │   └── order_models.py              # Order domain models
│   └── utils/
│       └── idempotency.py               # Webhook deduplication
├── tests/
│   ├── conftest.py
│   ├── test_config.py                   # Module 1
│   ├── test_health.py                   # Module 1
│   ├── test_webhook.py                  # Module 2
│   ├── test_whatsapp_client.py          # Module 2
│   ├── test_sheets_integration.py       # Module 3
│   ├── test_ai_service.py               # Module 4
│   └── test_end_to_end.py               # Module 5
├── data/
│   └── Food_Delivery_System.xlsx        # Local schema reference only
├── credentials/                         # .gitignored — put service_account.json here
├── .env                                 # .gitignored — your real secrets
├── .env.example                         # Safe placeholder template
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```
