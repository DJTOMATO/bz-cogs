import asyncio
import logging
import random
import re
from datetime import datetime, timezone

from redbot.core import Config, commands

from aiuser.generators.chat.generator import Chat_Generator

logger = logging.getLogger("red.bz_cogs.aiuser")


class ChatResponse():
    def __init__(self, ctx: commands.Context, config: Config, chat: Chat_Generator):
        self.ctx = ctx
        self.config = config
        self.response = None
        self.chat = chat

    async def send(self, standalone=False):
        message = self.ctx.message

        async with self.ctx.typing():
            self.response = await self.chat.generate_message()

        if not self.response:
            return

        await self.remove_patterns_from_response()

        if len(self.response) >= 2000:
            chunks = [self.response[i:i+2000] for i in range(0, len(self.response), 2000)]
            for chunk in chunks:
                await self.ctx.send(chunk)
        elif not standalone and await self.is_reply():
            await message.reply(self.response, mention_author=False)
        else:
            await self.ctx.send(self.response)

    async def remove_patterns_from_response(self) -> str:
        async def sub_with_timeout(pattern: re.Pattern, response):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(lambda: pattern.sub('', response).strip(' \n":')),
                    timeout=5
                )
                return result
            except asyncio.TimeoutError:
                logger.error(f"Timed out while applying regex pattern: {pattern.pattern}")
                return response

        patterns = await self.config.guild(self.ctx.guild).removelist_regexes()

        botname = self.ctx.message.guild.me.nick or self.ctx.bot.user.display_name
        patterns = [pattern.replace(r'{botname}', botname) for pattern in patterns]

        # get last 10 authors and applies regex patterns with display name
        authors = set()
        async for m in self.ctx.channel.history(limit=10):
            if m.author != self.ctx.guild.me:
                authors.add(m.author.display_name)

        authorname_patterns = list(filter(lambda pattern: r'{authorname}' in pattern, patterns))
        patterns = [pattern for pattern in patterns if r'{authorname}' not in pattern]

        for pattern in authorname_patterns:
            for author in authors:
                patterns.append(pattern.replace(r'{authorname}', author))

        patterns = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

        response = self.response.strip(' "')
        for pattern in patterns:
            response = await sub_with_timeout(pattern, response)
            if response.count('"') == 1:
                response = response.replace('"', '')
        self.response = response

    async def is_reply(self):
        if self.ctx.interaction:
            return False

        message = self.ctx.message
        try:
            await self.ctx.fetch_message(message.id)
        except:
            return False

        time_diff = datetime.now(timezone.utc) - message.created_at

        if time_diff.total_seconds() > 8 or random.random() < 0.25:
            return True

        try:
            async for last_message in message.channel.history(limit=1):
                if last_message.author == message.guild.me:
                    return True
        except:
            pass

        return False