"""WhatsApp channel adapter via Twilio."""
from __future__ import annotations

from typing import Any
from aiohttp import web

try:
    from twilio.rest import Client as TwilioClient
    HAS_TWILIO = True
except ImportError:
    HAS_TWILIO = False


class WhatsAppChannel:
    """Routes WhatsApp messages through CMAS gateway via Twilio webhooks."""

    def __init__(self, gateway: Any, twilio_sid: str, twilio_token: str, phone: str):
        self.gateway = gateway
        self.phone = phone
        if HAS_TWILIO:
            self.twilio = TwilioClient(twilio_sid, twilio_token)
        else:
            self.twilio = None
            print("[WhatsApp] twilio package not installed — webhook receive only")

    async def webhook_handler(self, request: web.Request) -> web.Response:
        """Handle incoming WhatsApp messages from Twilio webhook."""
        try:
            data = await request.post()
            phone = data.get("From", "")
            text = data.get("Body", "").strip()

            if not text:
                return web.Response(status=200)

            session_id = f"whatsapp_{phone.replace('+', '')}"
            user_id = phone

            response = await self.gateway.handle_user_message(
                session_id=session_id,
                user_id=user_id,
                channel="whatsapp",
                text=text,
            )

            # Reply via Twilio
            await self._send_reply(phone, response)

            return web.Response(status=200)
        except Exception as e:
            print(f"[WhatsApp] Webhook error: {e}")
            return web.Response(status=500)

    async def _send_reply(self, to: str, body: str):
        """Send a WhatsApp reply via Twilio."""
        if not self.twilio:
            print(f"[WhatsApp] Would send to {to}: {body[:100]}...")
            return
        try:
            self.twilio.messages.create(
                body=body[:1600],  # WhatsApp limit
                from_=f"whatsapp:{self.phone}",
                to=to if to.startswith("whatsapp:") else f"whatsapp:{to}",
            )
        except Exception as e:
            print(f"[WhatsApp] Send error: {e}")

    async def push_to_session(self, session_id: str, text: str):
        """Push a proactive message to a WhatsApp user."""
        if not session_id.startswith("whatsapp_"):
            return
        phone = "+" + session_id.replace("whatsapp_", "")
        await self._send_reply(phone, text)
