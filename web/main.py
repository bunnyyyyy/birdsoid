# main.py | main FastAPI routes and error handling
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

import random
import urllib.parse

from fastapi import Request
from fastapi.responses import HTMLResponse

from bot.data import birdList
from bot.filters import Filter, MediaType
from web import practice, user
from web.config import app
from web.data import logger
from web.functions import send_file, get_sciname, send_bird

app.include_router(practice.router)
app.include_router(user.router)


@app.get("/", response_class=HTMLResponse)
def api_index():
    logger.info("index page accessed")
    return "<h1>Hello!</h1><p>This is the index page for the Bird-ID internal API.<p>"


@app.get("/bird")
async def bird_info():
    logger.info("fetching random bird")
    bird = random.choice(birdList)
    logger.info(f"bird: {bird}")
    return {
        "bird": bird,
        "sciName": (await get_sciname(bird)),
        "imageURL": urllib.parse.quote(f"/image/{bird}"),
        "songURL": urllib.parse.quote(f"/song/{bird}"),
    }


@app.get("/image/{bird}")
async def bird_image(request: Request, bird: str):
    info = await send_bird(request, bird, MediaType.IMAGE, Filter())
    return send_file(info[0], media_type=info[2])


@app.get("/song/{bird}")
async def bird_song(request: Request, bird: str):
    info = await send_bird(request, bird, MediaType.SONG, Filter())
    return send_file(info[0], media_type=info[2])
