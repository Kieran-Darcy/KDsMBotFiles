import asyncio

import discord
import youtube_dl

from discord.ext import commands

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.10):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)




class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.nowPlaying = 0
        self.playlist = []
        self.stopped = False
        self.lock = asyncio.Lock()
        self.lock2 = asyncio.Lock()

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel = None):
        """Joins a voice channel"""

        userChan = ctx.author.voice                                         # Get user voice channel
        if channel is not None:
            if ctx.voice_client is not None:                                # Run If bot is in a voice channel
                return await ctx.voice_client.move_to(channel)              # Move the bot accross specified channels

            return await channel.connect()                                  # Connect bot to specified channel

        elif userChan is not None:                                          # Run If the user is in a voice channel
            if ctx.voice_client is not None:                                # Run If bot is in a voice channel
                return await ctx.voice_client.move_to(userChan.channel)     # Move the bot accross to user channel

            return await userChan.channel.connect()                         # Connect bot to users voice channel
        else:
            return await ctx.send('Please either join a voice channel or specify one!')


    @commands.command()
    async def play(self, ctx, *, query):
        """Plays a file from the local filesystem"""

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        ctx.voice_client.play(source, after=lambda e: print('Player error: %s' % e) if e else None)

        await ctx.send('Now playing: {}'.format(query))

    @commands.command()
    async def yt(self, ctx, *, url):
        """Plays from a url (almost anything youtube_dl supports)"""

        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=self.bot.loop)
            ctx.voice_client.play(player, after=lambda e: print('Player error: %s' % e) if e else None)

        await ctx.send('Now playing: {}'.format(player.title))
    
    @commands.command()
    async def stream(self, ctx, *, url):
        """Streams from a url (same as yt, but doesn't predownload)"""
        async with self.lock:
            if self.playlist != []:
                self.playlist = []
                self.nowPlaying = 0

        while await self.lock2.acquire():
            print("Aquired")
            url = await self.getNext(url)
            if url is None:
                self.lock2.release()
                print("Released")
                if not self.stopped:
                    await ctx.send('End of playlist!')
                break
            async with ctx.typing():    
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                ctx.voice_client.play(player, after= lambda e: print('Player error: %s' % e) if e else (self.lock2.release(), print("released")))

            await ctx.send('Now playing Item {} of {}:    {}'.format(self.nowPlaying+1, len(self.playlist), player.title))

    @commands.command()
    async def add(self, ctx, *, url):
        async with self.lock:
            self.playlist.append(url)   
            await ctx.send("Song Added") 

    async def getNext(self, url):
        async with self.lock:
            if self.playlist == []:
                self.playlist.append(url)
                return self.playlist[0]
            if len(self.playlist) > 1:
                self.nowPlaying += 1
                if len(self.playlist) <= self.nowPlaying:
                    return None
                return self.playlist[self.nowPlaying]
                

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("Changed volume to {}%".format(volume))

    @commands.command()
    async def pause(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
        else:
            ctx.voice_client.resume()
    
    @commands.command()
    async def resume(self, ctx):
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()

    @commands.command()
    async def stop(self, ctx):
        if ctx.voice_client.is_playing():
            async with self.lock:
                self.nowPlaying = len(self.playlist)
                self.stopped = True
            ctx.voice_client.stop()
        
    @commands.command()
    async def leave(self, ctx):
        """Stops and disconnects the bot from voice"""

        vc = ctx.voice_client
        if vc is not None:
            await ctx.send("Goodbye!")
            return await vc.disconnect()

    @play.before_invoke
    @yt.before_invoke
    @stream.before_invoke
    async def ensure_voice(self, ctx):
        self.stopped = False
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel!")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()



client = commands.Bot(command_prefix=commands.when_mentioned_or("$"),
                   description='Relatively simple music bot example')

@client.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(client.user))
    print('------')

client.add_cog(Music(client))

client.run('ODkwMzMxMzg4NTA5ODI3MTEz.YUuPuA.A0v8hAW6zg22_dzKLSQ0iv3FU7A')