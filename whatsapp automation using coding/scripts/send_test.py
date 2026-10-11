"""Send a test WhatsApp message via the Cloud API."""
import sys, asyncio
sys.path.insert(0, "src")

from app.integrations.whatsapp_client import WhatsAppClient

async def main():
    print("Sending WhatsApp message to your phone...")
    try:
        async with WhatsAppClient() as client:
            await client.send_text(
                to="917383702573",
                body="Welcome to Cloud Kitchen!\n\nI'm your AI food assistant. Ask me about our menu, place an order, or ask any question!\n\nTry saying:\n- What's on the menu?\n- I'd like to order butter chicken\n- What are your hours?"
            )
        print("SUCCESS - Message sent! Check your WhatsApp now.")
        print("Reply to it - your reply will trigger the webhook.")
    except Exception as e:
        print(f"FAILED: {e}")

asyncio.run(main())
