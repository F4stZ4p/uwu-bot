import discord
from discord.ext import commands
from discord.ext.commands import cooldown
from discord.ext.commands.cooldowns import BucketType
import time
import asyncio
import asyncpg
from datetime import datetime
from utils import errorhandler
import secrets
from random import choice

uwu_emote = "<:uwu:521394346688249856>"


class daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        uwulonian = await self.bot.redis.sismember("uwulonians", ctx.author.id)
        if uwulonian != 0:
            return True

        raise (errorhandler.hasUwU(ctx))

    @errorhandler.on_cooldown()
    @commands.command(description="Claim your daily uwus.", aliases=["daily"])
    async def dailies(self, ctx):
        await self.bot.pool.execute(
            "UPDATE user_stats SET uwus = user_stats.uwus + 500 WHERE user_id = $1",
            ctx.author.id,
        )
        await self.bot.redis.execute(
            "SET",
            f"{ctx.author.id}-{ctx.command.qualified_name}",
            "cooldown",
            "EX",
            86400,
        )
        await ctx.send(f"You claimed your daily 500 uwus!")


def setup(bot):
    bot.add_cog(daily(bot))
