# other.py | misc. commands
# Copyright (C) 2019-2021  EraserBird, person_v1.32, hmmm

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# import contextlib
# import os
import random
import string
from difflib import get_close_matches

import aiohttp
import discord
import wikipedia
from discord import app_commands
from discord.ext import commands

from bot.core import better_spellcheck, get_sciname, send_bird
from bot.data import (
    alpha_codes,
    birdListMaster,
    get_wiki_url,
    logger,
    memeList,
    sciListMaster,
    states,
    taxons,
)
from bot.filters import Filter, MediaType
from bot.functions import CustomCooldown, build_id_list, cache, decrypt_chacha

# Discord max message length is 2000 characters, leave some room just in case
MAX_MESSAGE = 1900


async def state_autocomplete(
    _: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=state, value=state)
        for state in states
        if current.lower() in state.lower()
    ][:25]


async def taxon_autocomplete(
    _: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=taxon, value=taxon)
        for taxon in taxons
        if current.lower() in taxon.lower()
    ][:25]


class Other(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def broken_join(input_list: list[str], max_size: int = MAX_MESSAGE) -> list[str]:
        pages: list[str] = []
        lines: list[str] = []
        block_length = 0
        for line in input_list:
            # add 2 to account for newlines
            if block_length + len(line) + 2 > max_size:
                page = "\n".join(lines)
                pages.append(page)
                lines.clear()
                block_length = 0
            lines.append(line)
            block_length += len(line) + 2

        if lines:
            page = "\n".join(lines)
            pages.append(page)

        return pages

    # Info - Gives call+image of 1 bird
    @commands.hybrid_command(
        brief="- Gives an image and call of a bird",
        help="- Gives an image and call of a bird. The bird name must come before any options.",
        usage="[bird] [options]",
        aliases=["i"],
    )
    @commands.check(CustomCooldown(5.0, bucket=commands.BucketType.user))
    @app_commands.rename(arg="bird_and_filters")
    @app_commands.describe(arg="The bird name must come before any options.")
    async def info(self, ctx, *, arg):
        logger.info("command: info")
        arg = arg.lower().strip()

        filters = Filter.parse(arg)
        if filters.vc:
            filters.vc = False
            await ctx.send("**The VC filter is not allowed here!**", ephemeral=True)

        options = filters.display()
        arg = arg.split(" ")

        bird = None

        if len(arg[0]) == 4:
            bird = alpha_codes.get(arg[0].upper())

        if not bird:
            for i in reversed(range(1, 6)):
                # try the first 5 words, then first 4, etc. looking for a match
                matches = get_close_matches(
                    string.capwords(" ".join(arg[:i]).replace("-", " ")),
                    birdListMaster + sciListMaster,
                    n=1,
                    cutoff=0.8,
                )
                if matches:
                    bird = matches[0]
                    break

        if not bird:
            await ctx.send(
                "Bird not found. Are you sure it's on the list?", ephemeral=True
            )
            return

        if ctx.interaction is None:
            delete = await ctx.send("Please wait a moment.")
        else:
            await ctx.typing()

        output_message = ""
        if options:
            output_message += f"**Detected filters**: `{'`, `'.join(options)}`\n"

        an = "an" if bird.lower()[0] in ("a", "e", "i", "o", "u") else "a"
        await send_bird(
            ctx,
            bird,
            MediaType.IMAGE,
            filters,
            message=output_message + f"Here's {an} *{bird.lower()}* image!",
        )
        await send_bird(
            ctx,
            bird,
            MediaType.SONG,
            filters,
            message=output_message + f"Here's {an} *{bird.lower()}* song!",
        )
        if ctx.interaction is None:
            await delete.delete()
        return

    @staticmethod
    @cache()
    async def bird_from_asset(asset_id: str):
        url = f"https://www.macaulaylibrary.org/asset/{asset_id}/embed"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text()
                currentBird = (
                    content.split("<title>")[1]
                    .split("</title>")[0]
                    .split(" - ")[1]
                    .lower()
                    .replace("-", " ")
                    .strip()
                )
        logger.info(f"asset found for {asset_id}: {currentBird}")
        return currentBird

    # Asset command - gives original Macaulay Library asset from asset code
    @commands.hybrid_command(
        help="- Gives the original Macaulay Library asset from an asset code",
        aliases=["source", "original", "orig"],
    )
    @commands.check(CustomCooldown(5.0, bucket=commands.BucketType.user))
    @app_commands.describe(
        code="The asset code to search for.",
        bird="The bird name that corresponds to the asset.",
    )
    async def asset(self, ctx, code: str, *, bird: str):
        logger.info("command: asset")

        guess = bird.strip().lower().replace("-", " ").strip()
        if not guess:
            await ctx.send(
                "Please provide the bird name to get the original asset.",
                ephemeral=True,
            )
            return

        try:
            asset = str(int(decrypt_chacha(code).hex(), 16))
            currentBird = await self.bird_from_asset(asset)
        except ValueError:
            await ctx.send("**Invalid asset code!**", ephemeral=True)
            return

        url = f"https://www.macaulaylibrary.org/asset/{asset}/"
        alpha_code = alpha_codes.get(string.capwords(currentBird), "")
        sciBird = (await get_sciname(currentBird)).lower().replace("-", " ")
        correct = (
            better_spellcheck(
                guess, [currentBird, sciBird], birdListMaster + sciListMaster
            )
            or guess.upper() == alpha_code
        )
        if correct or ((await self.bot.is_owner(ctx.author)) and guess == "please"):
            await ctx.send(f"**Here you go!**\n{url}")
        else:
            await ctx.send(
                "**Sorry, that's not the correct bird.**\n*Please try again.*",
                ephemeral=True,
            )

    # Filter command - lists available Macaulay Library filters and aliases
    @commands.hybrid_command(
        help="- Lists available Macaulay Library filters.", aliases=["filter"]
    )
    @commands.check(CustomCooldown(8.0, bucket=commands.BucketType.user))
    async def filters(self, ctx):
        logger.info("command: filters")
        filters = Filter.aliases()
        embed = discord.Embed(
            title="Media Filters",
            type="rich",
            description="Filters can be space-separated or comma-separated. "
            + "You can use any alias to set filters. "
            + "Please note media will only be shown if it "
            + "matches all the filters, so using filters can "
            + "greatly reduce the number of media returned.",
            color=discord.Color.green(),
        )
        embed.set_author(name="Bird ID - An Ornithology Bot")
        for title, subdict in filters.items():
            value = "".join(
                (
                    f"**{name.title()}**: `{'`, `'.join(aliases)}`\n"
                    for name, aliases in subdict.items()
                )
            )
            embed.add_field(name=title.title(), value=value, inline=False)
        await ctx.send(embed=embed)

    # List command - argument is state/bird list
    @commands.hybrid_command(
        help="- DMs the user with the appropriate bird list.", name="list"
    )
    @commands.check(CustomCooldown(5.0, bucket=commands.BucketType.user))
    @app_commands.describe(state="The specific bird list.")
    @app_commands.autocomplete(state=state_autocomplete)
    async def list_of_birds(self, ctx, state: str = "NATS"):
        logger.info("command: list")

        state = state.upper()

        if state not in states:
            logger.info("invalid state")
            await ctx.send(
                f"**Sorry, `{state}` is not a valid list.**\n*Valid Lists:* `{', '.join(map(str, list(states.keys())))}`",
                ephemeral=True,
            )
            return

        if ctx.interaction is not None:
            await ctx.typing()

        state_birdlist = sorted(
            build_id_list(
                user_id=ctx.author.id, state=state, media_type=MediaType.IMAGE
            )
        )
        state_songlist = sorted(
            build_id_list(user_id=ctx.author.id, state=state, media_type=MediaType.SONG)
        )

        birdLists = self.broken_join(state_birdlist)
        songLists = self.broken_join(state_songlist)

        if ctx.author.dm_channel is None:
            await ctx.author.create_dm()

        await ctx.author.dm_channel.send(f"**The {state} bird list:**")
        for birds in birdLists:
            await ctx.author.dm_channel.send(f"```\n{birds}```")

        await ctx.author.dm_channel.send(f"**The {state} bird songs:**")
        for birds in songLists:
            await ctx.author.dm_channel.send(f"```\n{birds}```")

        await ctx.send(
            f"The `{state}` bird list has **{len(state_birdlist)}** birds.\n"
            + f"The `{state}` bird list has **{len(state_songlist)}** songs.\n"
            + "*A full list of birds has been sent to you via DMs.*"
        )

    # taxons command - argument is state/bird list
    @commands.hybrid_command(
        help="- DMs the user with the appropriate bird list.",
        name="taxon",
        aliases=["taxons", "orders", "families", "order", "family"],
    )
    @commands.check(CustomCooldown(5.0, bucket=commands.BucketType.user))
    @app_commands.describe(
        taxon="The specific bird taxon", state="The specific bird list."
    )
    @app_commands.autocomplete(taxon=taxon_autocomplete, state=state_autocomplete)
    async def bird_taxons(
        self,
        ctx,
        taxon: str,
        state: str = "NATS",
    ):
        logger.info("command: taxons")

        taxon = taxon.lower()
        state = state.upper()

        if taxon not in taxons:
            logger.info("invalid taxon")
            await ctx.send(
                f"**Sorry, `{taxon if taxon else 'no taxon'}` is not a valid taxon.**\n*Valid taxons:* `{', '.join(map(str, list(taxons.keys())))}`",
                ephemeral=True,
            )
            return

        if state not in states:
            logger.info("invalid state")
            await ctx.send(
                f"**Sorry, `{state}` is not a valid state.**\n*Valid States:* `{', '.join(map(str, list(states.keys())))}`",
                ephemeral=True,
            )
            return

        if ctx.interaction is not None:
            await ctx.typing()

        bird_list = sorted(
            build_id_list(
                user_id=ctx.author.id,
                taxon=taxon,
                state=state,
                media_type=MediaType.IMAGE,
            )
        )
        song_bird_list = sorted(
            build_id_list(
                user_id=ctx.author.id,
                taxon=taxon,
                state=state,
                media_type=MediaType.SONG,
            )
        )
        if not bird_list and not song_bird_list:
            logger.info("no birds for taxon/state")
            await ctx.send(
                "**Sorry, no birds could be found for the taxon/state combo.**\n*Please try again*",
                ephemeral=True,
            )
            return

        birdLists = self.broken_join(bird_list)
        songLists = self.broken_join(song_bird_list)

        if ctx.author.dm_channel is None:
            await ctx.author.create_dm()

        await ctx.author.dm_channel.send(
            f"**The `{taxon}` in the `{state}` bird list:**"
        )
        for birds in birdLists:
            await ctx.author.dm_channel.send(f"```\n{birds}```")

        await ctx.author.dm_channel.send(
            f"**The `{taxon}` in the `{state}` bird songs:**"
        )
        for birds in songLists:
            await ctx.author.dm_channel.send(f"```\n{birds}```")

        await ctx.send(
            f"The `{taxon}` in the `{state}` bird list has **{len(bird_list)}** birds.\n"
            + f"The `{taxon}` in the `{state}` bird list has **{len(song_bird_list)}** songs.\n"
            + "*A full list of birds has been sent to you via DMs.*"
        )

    # Wiki command - argument is the wiki page
    @commands.hybrid_command(
        help="- Fetch the wikipedia page for any given argument", aliases=["wiki"]
    )
    @commands.check(CustomCooldown(5.0, bucket=commands.BucketType.user))
    @app_commands.rename(arg="query")
    @app_commands.describe(arg="A Wikipedia query")
    async def wikipedia(self, ctx, *, arg):
        logger.info("command: wiki")
        try:
            url = get_wiki_url(arg)
        except wikipedia.exceptions.DisambiguationError:
            await ctx.send(
                "Sorry, that page was not found. Try being more specific.",
                ephemeral=True,
            )
        except wikipedia.exceptions.PageError:
            await ctx.send("Sorry, that page was not found.", ephemeral=True)
        else:
            await ctx.send(url)

    # meme command - sends a random bird video/gif
    @commands.hybrid_command(help="- Sends a funny bird video!")
    @commands.check(
        CustomCooldown(180.0, disable=True, bucket=commands.BucketType.user)
    )
    async def meme(self, ctx):
        logger.info("command: meme")
        await ctx.send(random.choice(memeList))

    # Send command - for testing purposes only
    @commands.command(help="- send command", hidden=True, aliases=["sendas"])
    @commands.is_owner()
    async def send_as_bot(self, ctx, *, args):
        logger.info("command: send")
        logger.info(f"args: {args}")
        channel_id = int(args.split(" ")[0])
        message = args.strip(str(channel_id))
        channel = self.bot.get_channel(channel_id)
        await channel.send(message)
        await ctx.send("Ok, sent!")

    # # Test command - for testing purposes only
    # @commands.command(help="- test command", hidden=True)
    # @commands.is_owner()
    # async def cache(self, ctx):
    #     logger.info("command: cache stats")
    #     items = []
    #     with contextlib.suppress(FileNotFoundError):
    #         items += os.listdir("bot_files/cache/images/")
    #     with contextlib.suppress(FileNotFoundError):
    #         items += os.listdir("bot_files/cache/songs/")
    #     stats = {
    #         "sciname_cache": get_sciname.cache_info(),
    #         "taxon_cache": get_taxon.cache_info(),
    #         "num_downloaded_birds": len(items),
    #     }
    #     await ctx.send(f"```python\n{stats}```")

    # # Test command - for testing purposes only
    # @commands.command(help="- test command", hidden=True)
    # @commands.is_owner()
    # async def error(self, ctx):
    #     logger.info("command: error")
    #     await ctx.send(1 / 0)


async def setup(bot):
    await bot.add_cog(Other(bot))
