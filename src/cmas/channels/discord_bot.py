"""Discord channel adapter."""
from __future__ import annotations

from typing import Any

try:
    import discord
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False


class DiscordChannel:
    """Routes Discord messages through the CMAS gateway."""

    def __init__(self, gateway: Any, token: str):
        if not HAS_DISCORD:
            raise ImportError("discord.py is required: pip install discord.py")

        self.gateway = gateway
        self.token = token

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)

        @self.client.event
        async def on_ready():
            print(f"[Discord] Connected as {self.client.user}")

        @self.client.event
        async def on_message(message):
            if message.author.bot:
                return

            # Only respond to DMs or when mentioned
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self.client.user in message.mentions if message.guild else False

            if not is_dm and not is_mentioned:
                return

            text = message.content
            # Strip mention from text
            if is_mentioned and self.client.user:
                import re
                text = re.sub(f"<@!?{self.client.user.id}>", "", text).strip()

            if not text:
                return

            session_id = f"discord_{message.channel.id}"
            user_id = f"discord_{message.author.id}"

            async with message.channel.typing():
                try:
                    response = await self.gateway.handle_user_message(
                        session_id=session_id,
                        user_id=user_id,
                        channel="discord",
                        text=text,
                    )
                    # Discord has a 2000 char limit
                    for i in range(0, len(response), 2000):
                        await message.channel.send(response[i:i+2000])
                except Exception as e:
                    await message.channel.send(f"Error: {e}")

    async def start(self):
        """Start the Discord bot. Run as asyncio.create_task()."""
        await self.client.start(self.token)

    async def stop(self):
        await self.client.close()

    async def push_to_session(self, session_id: str, text: str):
        """Push a proactive message to a Discord channel."""
        # session_id format: "discord_{channel_id}"
        if not session_id.startswith("discord_"):
            return
        channel_id = int(session_id.replace("discord_", ""))
        channel = self.client.get_channel(channel_id)
        
        if not channel:
            try:
                channel = await self.client.fetch_channel(channel_id)
            except Exception:
                pass
                
        if channel:
            try:
                for i in range(0, len(text), 2000):
                    await channel.send(text[i:i+2000])
            except Exception:
                pass
