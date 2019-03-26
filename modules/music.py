import discord
from discord.ext import commands
import wavelink
import asyncio
import re
import aiohttp
import base64
import itertools
import math
from utils import errorhandler

urlRE = re.compile(r"https?:\/\/(?:www\.)?.+")
surl = re.compile("https:\/\/open.spotify.com?.+playlist\/([a-zA-Z0-9]+)")
album_re = re.compile("https:\/\/open.spotify.com?.+album\/([a-zA-Z0-9]+)")


class Track(wavelink.Track):
    __slots__ = ("requester", "channel", "message", "query", "ctx")

    def __init__(self, id_, info, *, query=None, ctx=None):
        super(Track, self).__init__(id_, info)
        self.ctx = ctx
        self.query = query

        self.requester = ctx.author
        self.channel = ctx.channel
        self.message = ctx.message

    @property
    def is_dead(self):
        return self.dead


class Player(wavelink.Player):
    def __init__(self, bot: commands.Bot, guild_id: int, node: wavelink.Node):
        super(Player, self).__init__(bot, guild_id, node)

        self.queue = asyncio.Queue()
        self.next_event = asyncio.Event()

        # default values for things like volume, DJ and eq

        self.volume = 50
        self.dj = None
        self.eq = "FLAT"
        self.inactive = False
        self.paused = False

        bot.loop.create_task(self.player_loop())

    @property
    def entries(self):
        return list(self.queue._queue)

    async def player_loop(self):
        await self.bot.wait_until_ready()
        # pre loop changes to player
        await self.set_preq("FLAT")
        await self.set_volume(self.volume)

        while True:
            self.next_event.clear()
            self.inactive = False

            song = await self.queue.get()
            if not song.id:
                songs = await self.bot.wavelink.get_tracks(f"ytsearch:{song.query}")

                if not songs:
                    continue
                try:
                    song_ = songs[0]
                    song = Track(id_=song_.id, info=song_.info, ctx=song.ctx)

                except Exception as er:
                    continue

            await self.play(song)

            embed = discord.Embed(color=0x7289DA)
            embed.set_author(name=f"Requested by {song.requester.name}")
            embed.description = f"[{song.title}]({song.uri})"
            await song.ctx.send(embed=embed, delete_after=20)

            await self.next_event.wait()


class Music(commands.Cog):
    """main cog for music playback"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        if not hasattr(bot, "wavelink"):
            self.bot.wavelink = wavelink.Client(bot)
        self.token = None

        bot.loop.create_task(self.initiate_nodes())

    def get_player(self, guild_id):
        return self.bot.wavelink.get_player(guild_id, cls=Player)

    async def initiate_nodes(self):
        node = await self.bot.wavelink.initiate_node(
            host="157.230.61.238",
            port=8080,
            rest_uri="http://157.230.61.238:8080/",
            password="C9gUMLdfU8MckGvbI6XMb7x+vatsVCiOB2R/y2Q=",
            identifier="uwu",
            region="na-east",
            secure=False,
        )
        node.set_hook(self.event_hook)

    async def cog_check(self, ctx):
        if await self.bot.redis.execute("GET", f"{ctx.author.id}-vote"):
            return True

        raise (errorhandler.hasVoted(ctx))

    def event_hook(self, event):
        if isinstance(event, wavelink.TrackEnd):
            event.player.next_event.set()

    def format_time(self, time):
        """ Formats the given time into HH:MM:SS. """
        hours, remainder = divmod(time / 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        return "%02d:%02d:%02d" % (hours, minutes, seconds)

    @commands.command(name="connect", aliases=["join", "summon"])
    async def _connect(self, ctx, *, channel: discord.VoiceChannel = None):
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                await ctx.caution("Unable to join channel...")

        player = self.get_player(ctx.guild.id)
        if player.is_connected:
            if ctx.author.voice.channel == ctx.guild.me.voice.channel:
                return

        await player.connect(channel.id)

    @commands.command(aliases=["pl"])
    async def play(self, ctx, *, query: str):

        await ctx.trigger_typing()
        await ctx.invoke(self._connect)

        query = query.strip("<>")

        player = self.get_player(ctx.guild.id)
        if not player.is_connected:
            return await ctx.caution("Please join a command channel...")

        if not urlRE.match(query):
            query = f"ytsearch:{query}"

        embed = discord.Embed(color=0x7289DA)

        songs = await self.bot.wavelink.get_tracks(query)
        if not songs:
            return await ctx.caution("No song found...")

        if isinstance(songs, wavelink.TrackPlaylist):
            for t in songs.tracks:
                await player.queue.put(Track(t.id, t.info, ctx=ctx))

            embed.set_author(name=f"Playlist queued by {ctx.author}")
            embed.description = (
                f"[{songs.data['playlistInfo']['name']}]({songs.tracks[0].uri})"
            )
            await ctx.send(embed=embed, delete_after=20)

        else:
            song = songs[0]
            embed.set_author(name=f"Song queued by {ctx.author}")
            embed.description = f"[{song.title}]({song.uri})"
            await ctx.send(embed=embed, delete_after=20)
            await player.queue.put(Track(id_=song.id, info=song.info, ctx=ctx))

    @commands.command(aliases=["np", "playing", "music_player"])
    async def now(self, ctx):
        player = self.get_player(ctx.guild.id)
        if not player.is_playing:
            return await ctx.caution("I am not playing...")

        position = self.format_time(player.position)
        if player.current.is_stream == True:
            duration = ":red_circle: Live"
        else:
            duration = self.format_time(player.current.duration)

        embed = discord.Embed(
            color=0x7289DA,
            description=f"[{player.current.title}]({player.current.uri})\nRequested By - {player.current.requester}\nVolume - {player.volume}\n Duration - {position}/{duration}",
            title=f"Now playing:",
        )
        embed.set_thumbnail(url=player.current.thumb)
        await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx):
        player = self.get_player(ctx.guild.id)
        if not player.is_playing:
            return await ctx.caution("I am not playing...")

        await player.stop()
        await ctx.send(f"Song skipped by {ctx.author}!")

    @commands.command()
    async def stop(self, ctx):
        player = self.get_player(ctx.guild.id)
        if not player.is_playing:
            return await ctx.caution("I am not playing...")

        player.queue._queue.clear()
        await player.stop()
        await player.disconnect()
        await ctx.send("Stopped", delete_after=15)

    @commands.command()
    async def queue(self, ctx, page: int = 1):
        player = self.get_player(ctx.guild.id)

        if len(player.entries) == 0:
            return await ctx.caution("Nothing in queue!")

        item_per_page = 10
        pages = math.ceil(len(player.entries) / item_per_page)

        start = (page - 1) * item_per_page
        end = start + item_per_page

        text = ""

        upcomming = list(itertools.islice(player.entries, start, end))
        for index, track in enumerate(upcomming):
            text += f"[{index + 1}] - [{track.title}]({track.uri})\n"

        embed = discord.Embed(colour=0x7289DA, description=text)
        embed.set_author(
            name=f"{len(player.entries)} songs in the queue ({page}/{pages})"
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def pause(self, ctx):
        player = self.get_player(ctx.guild.id)

        if player.paused == False:
            await player.set_pause(True)
            player.paused = True
            await ctx.send("Paused")
        else:
            await player.set_pause(False)
            player.paused = False
            await ctx.send("Unpaused")

    @commands.command()
    async def volume(self, ctx, amount = None):
        player = self.get_player(ctx.guild.id)
        if amount is None:
            return await ctx.send(f"Current player volume: {player.volume}")
        if amount <= 100 and amount > 0 or amount == 0:
            await player.set_volume(amount)
            player.volume = amount
            await ctx.send(f"Volume set to {amount}%")
        else:
            return await ctx.send("Invalid volume. Please use 1-100")

    @commands.command()
    async def eq(self, ctx, eq: str = None):
        player = self.get_player(ctx.guild.id)
        if not eq:
            await player.set_preq("FLAT")
            await ctx.send("Available EQs:\n deathsBoost \n  Metal\n Piano\n")
        else:
            eqs = ["flat", "boost", "metal", "piano"]
            if not eq.lower() in eqs:
                return await ctx.caution("Invalid EQ.")
            await player.set_preq(eq.upper())
            await ctx.send(f"Set EQ to {eq}")

    @commands.command()
    async def remove(self, ctx, item: int = None):
        player = self.get_player(ctx.guild.id)

        if not item:
            return await ctx.caution(
                "Please specify which queue item you would like to remove..."
            )

        try:
            index = item - 1
            song = player.entries[index]
            player.queue._queue.remove(player.entries[index])
        except IndexError:
            return await ctx.caution("Invalid...")

        embed = discord.Embed(colour=0x7289DA)
        embed.set_author(name=f"{song.title} removed!")
        await ctx.send(embed=embed)

    @commands.command(aliases=["dc"])
    async def disconnect(self, ctx):
        player = self.get_player(ctx.guild.id)

        await player.stop()
        player.queue._queue.clear()
        await player.disconnect()
        await ctx.send("bye~ uwu")


def setup(bot):
    bot.add_cog(Music(bot))
