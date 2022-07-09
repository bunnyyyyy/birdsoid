# core.py | core media fetching functions
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

import asyncio
import collections
import contextlib
import difflib
import functools
import math
import os
import random
import shutil
import string
import urllib
from io import BytesIO
from typing import Iterable, Tuple

import aiohttp
import discord
import eyed3
from PIL import Image
from sentry_sdk import capture_exception

import bot.voice as voice_functions
from bot.data import GenericError, birdListMaster, database, logger, screech_owls
from bot.filters import Filter, MediaType
from bot.functions import cache, encrypt_chacha

# Macaulay URL definitions
SCINAME_URL = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&species={}"
TAXON_CODE_URL = (
    "https://taxonomy.api.macaulaylibrary.org/v1/taxonomy?q={}&key=PUB5447877383"
)
ASSET_URL = "https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{id}/{size}"

COUNT = 5  # fetch 5 media from macaulay at a time

MAX_FILESIZE = 6000000  # limit media to 6mb


class CookieManager:
    def __init__(self):
        self._cookies: aiohttp.CookieJar = None

    @staticmethod
    async def _get_cookies():
        async with aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.82 Safari/537.36"
            }
        ) as session:
            await session.head("https://search.macaulaylibrary.org/login?path=/catalog")
            return session.cookie_jar

    async def __call__(self):
        if self._cookies is None or database.get("cookies.expired:global") is None:
            database.set("cookies.expired:global", "false")
            database.expire("cookies.expired:global", 60 * 60 * 24 * 5)  # 5 days
            self._cookies = await self._get_cookies()
        return self._cookies

    def clear(self):
        self._cookies = None


cookies = CookieManager()


@cache(pre=lambda x: string.capwords(x.strip().replace("-", " ")), local=False)
async def get_sciname(bird: str, session=None, retries=0) -> str:
    """Returns the scientific name of a bird.

    Scientific names are found using the eBird API from the Cornell Lab of Ornithology,
    using `SCINAME_URL` to fetch data.
    Raises a `GenericError` if a scientific name is not found or an HTTP error occurs.

    `bird` (str) - common/scientific name of the bird you want to look up\n
    `session` (optional) - an aiohttp client session
    """
    logger.info(f"getting sciname for {bird}")
    async with contextlib.AsyncExitStack() as stack:
        if session is None:
            session = await stack.enter_async_context(
                aiohttp.ClientSession(cookie_jar=(await cookies()))
            )
        try:
            code = (await get_taxon(bird, session))[0]
        except GenericError as e:
            if e.code == 111:
                code = bird
            else:
                raise

        sciname_url = SCINAME_URL.format(urllib.parse.quote(code))
        async with session.get(sciname_url) as sciname_response:
            if sciname_response.status != 200:
                if retries >= 3:
                    logger.info("Retried more than 3 times. Aborting...")
                    raise GenericError(
                        f"An http error code of {sciname_response.status} occurred"
                        + f" while fetching {sciname_url} for {bird}",
                        code=201,
                    )
                retries += 1
                logger.info(
                    f"An HTTP error occurred; Retries: {retries}; Sleeping: {1.5**retries}"
                )
                await asyncio.sleep(1.5**retries)
                sciname = await get_sciname(bird, session, retries)
                return sciname

            sciname_data = await sciname_response.json()
            try:
                sciname = sciname_data[0]["sciName"]
            except IndexError as e:
                raise GenericError(f"No sciname found for {code}", code=111) from e
    logger.info(f"sciname: {sciname}")
    return sciname


@cache(pre=lambda x: string.capwords(x.strip().replace("-", " ")), local=False)
async def get_taxon(bird: str, session=None, retries=0) -> Tuple[str, str]:
    """Returns the taxonomic code of a bird.

    Taxonomic codes are used by the Cornell Lab of Ornithology to identify species of birds.
    This function uses the Macaulay Library's internal API to fetch the taxon code
    from the common or scientific name, using `TAXON_CODE_URL`.
    Raises a `GenericError` if a code is not found or if an HTTP error occurs.

    `bird` (str) - common/scientific name of bird you want to look up\n
    `session` (optional) - an aiohttp client session
    """
    logger.info(f"getting taxon code for {bird}")
    async with contextlib.AsyncExitStack() as stack:
        if session is None:
            session = await stack.enter_async_context(
                aiohttp.ClientSession(cookie_jar=(await cookies()))
            )
        taxon_code_url = TAXON_CODE_URL.format(
            urllib.parse.quote(bird.replace("-", " ").replace("'s", ""))
        )
        async with session.get(taxon_code_url) as taxon_code_response:
            if taxon_code_response.status != 200:
                if retries >= 3:
                    logger.info("Retried more than 3 times. Aborting...")
                    raise GenericError(
                        f"An http error code of {taxon_code_response.status} occurred"
                        + f" while fetching {taxon_code_url} for {bird}",
                        code=201,
                    )
                retries += 1
                logger.info(
                    f"An HTTP error occurred; Retries: {retries}; Sleeping: {1.5**retries}"
                )
                await asyncio.sleep(1.5**retries)
                return await get_taxon(bird, session, retries)

            taxon_code_data = await taxon_code_response.json()
            try:
                logger.info(f"raw data: {taxon_code_data}")

                first_item = taxon_code_data[0]
                taxon_code = first_item["code"]
                item_name = first_item["name"]
                logger.info(f"first item: {first_item}")

                if len(taxon_code_data) > 1:
                    logger.info("entering check")
                    for item in taxon_code_data:
                        logger.info(f"checking: {item}")
                        common, sci_name = item["name"].split(" - ")
                        if (  # spellcheck
                            spellcheck(common, bird, 4) or spellcheck(sci_name, bird, 4)
                        ) and (  # ensure that it's a species by checking for binomial name
                            " " in sci_name
                        ):
                            logger.info("ok")
                            taxon_code = item["code"]
                            item_name = item["name"]
                            break
                        logger.info("fail")
            except IndexError as e:
                raise GenericError(f"No taxon code found for {bird}", code=111) from e
    logger.info(f"taxon code: {taxon_code}")
    logger.info(f"name: {item_name}")
    return (taxon_code, item_name)


ValidatedBird = collections.namedtuple(
    "ValidatedBird", ["input_bird", "valid", "reason", "detected_name"]
)


async def valid_bird(bird: str, session=None) -> ValidatedBird:
    """Checks if a bird is valid.

    This checks first if Macaulay has a valid taxon code for the bird,
    then if the bird is already in one of our lists. If not, then it checks
    if Macaulay has valid images for the bird.

    Returns a tuple: `(input bird, valid bool, reason, detected name (may be empty string))`.
    """
    bird_ = string.capwords(bird.strip().replace("-", " "))
    logger.info(f"checking if {bird} is valid")
    async with contextlib.AsyncExitStack() as stack:
        if session is None:
            session = await stack.enter_async_context(
                aiohttp.ClientSession(cookie_jar=(await cookies()))
            )
        try:
            name = (await get_taxon(bird_, session))[1]
        except GenericError as e:
            if e.code in (111, 201):
                return ValidatedBird(bird, False, "No taxon code found", "")
            raise e
        if bird_ not in birdListMaster:
            try:
                urls = await _get_urls(session, bird_, MediaType.IMAGE, Filter())
            except GenericError as e:
                if e.code in (100, 201):
                    return ValidatedBird(bird, False, "One or less images found", name)
                raise e
            if len(urls) < 2:
                return ValidatedBird(bird, False, "One or less images found", name)
    return ValidatedBird(bird, True, "All checks passed", name)


def _black_and_white(input_image_path) -> BytesIO:
    """Returns a black and white version of an image.

    Output type is a file object (BytesIO).

    `input_image_path` - path to image (string) or file object
    """
    logger.info("black and white")
    with Image.open(input_image_path) as color_image:
        bw = color_image.convert("L")
        final_buffer = BytesIO()
        bw.save(final_buffer, "png")
    final_buffer.seek(0)
    return final_buffer


async def send_bird(
    ctx, bird: str, media_type: MediaType, filters: Filter, on_error=None, message=None
):
    """Gets bird media and sends it to the user.

    `ctx` - Discord context object\n
    `bird` (str) - bird to send\n
    `media_type` (MediaType) - type of media (images/songs)\n
    `filters` (bot.filters Filter)\n
    `on_error` (function) - async function to run when an error occurs, passes error as argument\n
    `message` (str) - text message to send before bird\n
    """
    if bird == "":
        logger.error("error - bird is blank")
        await ctx.send("**There was an error fetching birds.**")
        if on_error is not None:
            await on_error(GenericError("bird is blank", code=100))
        else:
            await ctx.send("*Please try again.*")
        return

    # add special condition for screech owls
    # since screech owl is a genus and SciOly
    # doesn't specify a species
    if bird == "Screech Owl":
        logger.info("choosing specific Screech Owl")
        bird = random.choice(screech_owls)

    delete = await ctx.send("**Fetching.** This may take a while.")
    # trigger "typing" discord message
    await ctx.trigger_typing()

    try:
        filename, extension = await get_media(ctx, bird, media_type, filters)
        macaulay_asset_id = filename.split("/")[-1].split(".")[0]
    except GenericError as e:
        await delete.delete()
        if e.code == 100:
            await ctx.send(
                f"**This combination of filters has no valid {media_type.name()} for the current bird.**"
            )
        elif e.code == 201:
            capture_exception(e)
            logger.exception(e)
            await ctx.send(
                "**A network error has occurred.**\n*Please try again later.*"
            )
            database.incrby("cooldown:global", amount=1)
            database.expire("cooldown:global", 300)
        else:
            capture_exception(e)
            logger.exception(e)
            await ctx.send(
                f"**An error has occurred while fetching {media_type.name()}.**\n**Reason:** {e}"
            )
        if on_error is not None:
            await on_error(e)
        else:
            await ctx.send("*Please try again.*")
        return

    if os.stat(filename).st_size > MAX_FILESIZE:  # another filesize check (4mb)
        await delete.delete()
        await ctx.send("**Oops! File too large :(**\n*Please try again.*")
        return

    if media_type is MediaType.IMAGE:
        if filters.bw:
            # prevent the black and white conversion from blocking
            loop = asyncio.get_running_loop()
            fn = functools.partial(_black_and_white, filename)
            filename = await loop.run_in_executor(None, fn)

    elif media_type is MediaType.SONG and not filters.vc:
        # remove spoilers in tag metadata
        audio_file = eyed3.load(filename)
        if audio_file is not None and audio_file.tag is not None:
            audio_file.tag.remove(filename)

    if message is not None:
        await ctx.send(message)

    if macaulay_asset_id:
        await ctx.send(
            "**Asset Code**: `"
            + encrypt_chacha(int(macaulay_asset_id).to_bytes(8, "big").strip(b"\x00"))
            + "`"
        )

    if media_type is MediaType.SONG and filters.vc:
        await voice_functions.play(ctx, filename)
    else:
        # change filename to avoid spoilers
        file_obj = discord.File(filename, filename=f"bird.{extension}")
        await ctx.send(file=file_obj)
    await delete.delete()


async def get_media(ctx, bird: str, media_type: MediaType, filters: Filter):
    """Chooses media from a list of filenames.

    This function chooses a valid image to pass to send_bird().
    Valid images are based on file extension and size. (8mb discord limit)

    Returns a list containing the file path and extension type.

    `ctx` - Discord context object\n
    `bird` (str) - bird to get media of\n
    `media_type` (MediaType) - type of media (images/songs)\n
    `filters` (bot.filters Filter)\n
    """

    # fetch scientific names of birds
    try:
        sciBird = await get_sciname(bird)
    except GenericError:
        sciBird = bird
    media = await get_files(sciBird, media_type, filters)
    logger.info("media: " + str(media))
    prevJ = int(database.hget(f"channel:{ctx.channel.id}", "prevJ"))
    # Randomize start (choose beginning 4/5ths in case it fails checks)
    if media:
        j = (prevJ + 1) % len(media)
        logger.info("prevJ: " + str(prevJ))
        logger.info("j: " + str(j))

        for x in range(0, len(media)):  # check file type and size
            y = (x + j) % len(media)
            path = media[y]
            extension = path.split(".")[-1]
            logger.info("extension: " + str(extension))
            statInfo = os.stat(path)
            logger.info("size: " + str(statInfo.st_size))
            if (
                extension.lower() in media_type.types().values()
                and statInfo.st_size < MAX_FILESIZE
            ):  # keep files less than 4mb
                logger.info("found one!")
                break
            raise GenericError(f"No Valid {media_type.name().title()} Found", code=999)

        database.hset(f"channel:{ctx.channel.id}", "prevJ", str(j))
    else:
        raise GenericError(f"No {media_type.name().title()} Found", code=100)

    return [path, extension]


async def get_files(
    sciBird: str, media_type: MediaType, filters: Filter, retries: int = 0
):
    """Returns a list of image/song filenames.

    This function also does cache management,
    looking for files in the cache for media and
    downloading images to the cache if not found.

    `sciBird` (str) - scientific name of bird\n
    `media_type` (MediaType) - type of media (images/songs)\n
    `filters` (bot.filters Filter)\n
    """
    logger.info(f"get_files retries: {retries}")
    directory = f"bot_files/cache/{media_type.name()}/{sciBird}{filters.to_int()}/"
    # track counts for more accurate eviction
    database.zincrby(
        "frequency.media:global",
        1,
        f"{media_type.name()}/{sciBird}{filters.to_int()}",
    )
    try:
        logger.info("trying")
        files_dir = os.listdir(directory)
        logger.info(directory)
        if not files_dir:
            raise GenericError("No Files", code=100)
        return [f"{directory}{path}" for path in files_dir]
    except (FileNotFoundError, GenericError):
        logger.info("fetching files")
        # if not found, fetch images
        logger.info("scibird: " + str(sciBird))
        filenames = await download_media(sciBird, media_type, filters, directory)
        if not filenames:
            if retries < 3:
                retries += 1
                return await get_files(sciBird, media_type, filters, retries)
            logger.info("More than 3 retries")

        return filenames


async def download_media(
    bird: str, media_type: MediaType, filters: Filter, directory=None, session=None
):
    """Returns a list of filenames downloaded from Macaulay Library.

    This function manages the download helpers to fetch images from Macaulay.

    `bird` (str) - scientific name of bird\n
    `media_type` (MediaType) - type of media (images/songs)\n
    `filters` (bot.filters Filter)\n
    `directory` (str) - relative path to bird directory\n
    `session` (aiohttp ClientSession)
    """
    if directory is None:
        directory = f"bot_files/cache/{media_type.name()}/{bird}{filters.to_int()}/"

    async with contextlib.AsyncExitStack() as stack:
        if session is None:
            session = await stack.enter_async_context(
                aiohttp.ClientSession(cookie_jar=(await cookies()))
            )
        urls = await _get_urls(session, bird, media_type, filters)
        if not os.path.exists(directory):
            os.makedirs(directory)
        urls = [(f"{directory}{asset_id}", url) for url, asset_id in urls]
        sem = asyncio.BoundedSemaphore(3)
        filenames = await asyncio.gather(
            *(_download_helper(path, url, session, sem) for path, url in urls)
        )
        fails = filenames.count(None)
        if None in filenames:
            filenames = set(filenames)
            filenames.discard(None)
            filenames = list(filenames)
        logger.info(f"downloaded {media_type.name()} for {bird}")
        logger.info(f"download check fails: {fails}")
        logger.info(f"returned filename count: {len(filenames)}")
        logger.info(f"actual filenames count: {len(os.listdir(directory))}")
        return filenames


async def _get_urls(
    session: aiohttp.ClientSession,
    bird: str,
    media_type: MediaType,
    filters: Filter,
    retries: int = 0,
):
    """Returns a list of urls to Macaulay Library media.

    The amount of urls returned is specified in `COUNT`.
    Media URLs are fetched using Macaulay Library's internal JSON API,
    with `CATALOG_URL`. Raises a `GenericError` if fails.\n
    Some urls may return an error code of 476 (because it is still being processed),
    if so, ignore that url.

    `session` (aiohttp ClientSession)\n
    `bird` (str) - can be either common name or scientific name\n
    `media_type` (MediaType) - either `p` for pictures, `a` for audio, or `v` for video\n
    `filters` (bot.filters Filter)
    """
    logger.info(f"getting file urls for {bird}")
    taxon_code = (await get_taxon(bird, session))[0]
    database_key = f"{media_type.name()}/{bird}{filters.to_int()}"
    cursor = (database.get(f"media.cursor:{database_key}") or b"").decode()
    catalog_url = filters.url(taxon_code, media_type, COUNT, cursor)

    async with session.get(catalog_url) as catalog_response:
        if catalog_response.status != 200:
            cookies.clear()
            if retries >= 3:
                logger.info("Retried more than 3 times. Aborting...")
                raise GenericError(
                    f"An http error code of {catalog_response.status} occurred "
                    + f"while fetching {catalog_url} for a {media_type.name()} for {bird}",
                    code=201,
                )
            retries += 1
            logger.info(
                f"An HTTP error occurred; Retries: {retries}; Sleeping: {1.5**retries}"
            )
            await asyncio.sleep(1.5**retries)
            urls = await _get_urls(session, bird, media_type, filters, retries)
            return urls

        catalog_data = await catalog_response.json()
        if catalog_data and "cursorMark" in catalog_data[-1]:
            cursor_mark = catalog_data[-1]["cursorMark"]
        else:
            cursor_mark = b""
        database.set(f"media.cursor:{database_key}", cursor_mark)

        if media_type is MediaType.IMAGE:
            if filters.large:
                size = "1200"
            else:
                size = "640"
        else:
            size = "audio"

        urls = [
            (ASSET_URL.format(id=data["assetId"], size=size), data["assetId"])
            for data in catalog_data
        ]
        if not urls:
            if retries >= 1:
                raise GenericError("No urls found.", code=100)
            logger.info("retrying without cursor")
            retries += 1
            urls = await _get_urls(session, bird, media_type, filters, retries)
            return urls

        return urls


async def _download_helper(path, url, session, sem):
    """Downloads media from the given URL.

    Returns the file path to the downloaded item.

    `path` (str) - path with filename of location to download, no extension\n
    `url` (str) - url to the item to be downloaded\n
    `session` (aiohttp ClientSession)
    """
    async with sem:
        try:
            async with session.get(url) as response:
                media_size = response.headers.get("content-length")
                if (
                    response.status != 200
                    or media_size is None
                    or int(media_size) > MAX_FILESIZE
                ):
                    logger.info(f"FAIL: status: {response.status}; size: {media_size}")
                    logger.info(url)
                    return None

                # from https://stackoverflow.com/questions/29674905/convert-content-type-header-into-file-extension
                content_type = (
                    response.headers["content-type"].partition(";")[0].strip()
                )
                if content_type.partition("/")[0] == "image":
                    try:
                        ext = MediaType.IMAGE.types()[content_type]
                    except KeyError as e:
                        raise GenericError(
                            f"No valid extensions found. Content-Type: {content_type}"
                        ) from e

                elif content_type.partition("/")[0] == "audio":
                    try:
                        ext = MediaType.SONG.types()[content_type]
                    except KeyError as e:
                        raise GenericError(
                            f"No valid extensions found. Content-Type: {content_type}"
                        ) from e
                else:
                    raise GenericError("Invalid content-type.")

                filename = f"{path}.{ext}"
                # from https://stackoverflow.com/questions/38358521/alternative-of-urllib-urlretrieve-in-python-3-5
                with open(filename, "wb") as out_file:
                    block_size = 1024 * 8
                    while True:
                        block = await response.content.read(
                            block_size
                        )  # pylint: disable=no-member
                        if not block:
                            break
                        out_file.write(block)
                return filename

        except aiohttp.ClientError as e:
            logger.info(f"Client Error with url {url} and path {path}")
            capture_exception(e)
            raise


# def rotate_cache():
#     """Deletes a random selection of cached birds."""
#     logger.info("Rotating cache items")
#     items = []
#     with contextlib.suppress(FileNotFoundError):
#         items += map(
#             lambda x: f"bot_files/cache/images/{x}/",
#             os.listdir("bot_files/cache/images/"),
#         )
#     with contextlib.suppress(FileNotFoundError):
#         items += map(
#             lambda x: f"bot_files/cache/songs/{x}/",
#             os.listdir("bot_files/cache/songs/"),
#         )
#     logger.info(f"num birds: {len(items)}")
#     delete = random.choices(
#         items, k=math.ceil(len(items) * 0.05)
#     )  # choose 5% of the items to delete
#     for directory in delete:
#         shutil.rmtree(directory)
#         logger.info(f"{directory} removed")


def evict_media():
    """Deletes media for items that have exceeded a certain frequency.

    This prevents media from becoming stale. If the item frequency has
    been incremented more than 2*COUNT times, this function will delete
    the top 3 items.
    """
    logger.info("Updating cached images")

    for item in map(
        lambda x: x.decode(),
        database.zrevrangebyscore(
            "frequency.media:global",
            "+inf",
            min=2 * COUNT,
            start=0,
            num=3,
        ),
    ):
        database.zadd("frequency.media:global", {item: 0})
        shutil.rmtree(f"bot_files/cache/{item}/")
        logger.info(f"{item} removed")


def spellcheck(arg, correct, cutoff=None):
    """Checks if two words are close to each other.

    `worda` (str) - first word to compare
    `wordb` (str) - second word to compare
    `cutoff` (int) - allowed difference amount
    """
    if cutoff is None:
        cutoff = min((4, math.floor(len(correct) / 3)))
    arg = arg.lower().replace("-", " ").replace("'", "")
    correct = correct.lower().replace("-", " ").replace("'", "")
    shorterword = min(arg, correct, key=len)
    if arg != correct:
        if (
            len(list(difflib.Differ().compare(arg, correct))) - len(shorterword)
            >= cutoff
        ):
            return False
    return True


def spellcheck_list(arg, correct_options, cutoff=None):
    for correct in correct_options:
        if spellcheck(arg, correct, cutoff):
            return True
    return False


def better_spellcheck(
    word: str, correct: Iterable[str], options: Iterable[str]
) -> bool:
    """Allow lenient spelling unless another answer is closer."""
    all_options = set(list(correct) + list(options))
    matches = difflib.get_close_matches(
        word.lower(), map(str.lower, all_options), n=1, cutoff=(2 / 3)
    )
    if not matches:
        return False
    if matches[0] in map(str.lower, correct):
        return True
    return False
