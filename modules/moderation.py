from discord.ext import commands
import discord
from utils import errorhandler
import asyncpg
from datetime import datetime
import copy
from typing import Union
import inspect
import textwrap
from contextlib import redirect_stdout
import io
import traceback


class MemberID(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            m = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(
                    f"{argument} is not a valid member or ID."
                ) from None
        else:
            can_execute = (
                ctx.author.id == ctx.bot.owner_id
                or ctx.author == ctx.guild.owner
                or ctx.author.top_role > m.top_role
            )

            if not can_execute:
                raise commands.BadArgument(
                    "You cannot perform this action due to role hierarchy."
                )
            return m.id


class BannedMember(commands.Converter):
    async def convert(self, ctx, argument):
        ban_list = await ctx.guild.bans()
        try:
            member_id = int(argument, base=10)
            entity = discord.utils.find(lambda u: u.user.id == member_id, ban_list)
        except ValueError:
            entity = discord.utils.find(lambda u: str(u.user) == argument, ban_list)
        if entity is None:
            raise commands.BadArgument("That user wasn't previously banned...")
        return entity


class moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(ban_members=True)
    @commands.command(
        description="Softbans a user. Ban then unban to delete messages",
        brief="Softbans user",
        usage="softban [user] [reason]",
    )
    async def softban(self, ctx, user: discord.Member, *, reason=None):
        if reason is None:
            reason = f"No reason"

        await ctx.guild.ban(user, reason=f"[SOFTBAN] {user.id} for {reason}")
        await ctx.guild.unban(user, reason=f"[SOFTBAN UNBAN]")

        await ctx.send(f"Softbanned {user} for {reason}")

    @commands.has_permissions(ban_members=True)
    @commands.command(
        description="Bans a user", usage="ban [user] [reason]", brief="Bans user"
    )
    async def ban(self, ctx, user: MemberID, *, reason=None):
        if reason is None:
            reason = "No reason"

        await ctx.guild.ban(
            discord.Object(id=user), reason=f"[BAN] {user} for {reason}"
        )
        await ctx.send(f"Banned {user} for {reason}")

    @commands.has_permissions(kick_members=True)
    @commands.command(
        description="Kicks a user", usage="kick [user] [reason]", brief="Kick user"
    )
    async def kick(self, ctx, user: discord.Member, *, reason=None):
        if reason is None:
            reason = "No reason"

        await ctx.guild.kick(user, reason=f"[KICK] {user.id} for {reason}")
        await ctx.send(f"Kicked {user} for {reason}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def prefix(self, ctx, *, prefix: str):
        try:
            if len(prefix) > 512:
                return await ctx.caution(
                    "You can't have a prefix with more than 512 characters."
                )
            if self.bot.prefixes.get(ctx.guild.id):
                await self.bot.pool.execute(
                    "UPDATE guild_prefixes SET prefix = $1 WHERE guild_id = $2",
                    prefix,
                    ctx.guild.id,
                )
            else:
                await self.bot.pool.execute(
                    "INSERT INTO guild_prefixes (guild_id, prefix) VALUES ($1, $2)",
                    ctx.guild.id,
                    prefix,
                )
            self.bot.prefixes[ctx.guild.id] = prefix
            await ctx.send(f"Set guild prefix to `{prefix}`.")
        except Exception as e:
            await ctx.send(e)


def setup(bot):
    bot.add_cog(moderation(bot))
