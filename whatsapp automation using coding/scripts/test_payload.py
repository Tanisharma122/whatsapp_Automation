"""Quick validation test — find exactly why payloads are rejected."""
import sys, json, time
sys.path.insert(0, "src")

from app.models.whatsapp import WhatsAppWebhookPayload

payload = json.loads(r'''
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "1421999272665276",
    "changes": [{
      "field": "messages",
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15556338140", "phone_number_id": "1269644716243321"},
        "contacts": [{"profile": {"name": "Tanisha"}, "wa_id": "917383702573"}],
        "messages": [{
          "from": "917383702573",
          "id": "wamid.test123",
          "timestamp": "''' + str(int(time.time())) + r'''",
          "text": {"body": "Hello what food do you serve?"},
          "type": "text"
        }]
      }
    }]
  }]
}
''')

try:
    result = WhatsAppWebhookPayload.model_validate(payload)
    print("VALIDATION OK")
    msg = result.entry[0].changes[0].value.messages[0]
    print(f"From: {msg.from_}")
    print(f"Text: {msg.get_text_body()}")
except Exception as e:
    print(f"VALIDATION FAILED:\n{e}")
