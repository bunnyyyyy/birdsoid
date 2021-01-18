# config.py | Flask server config
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
import random

from flask import session

from bot.data import database, logger
from bot.functions import user_setup
from web_old.config import DATABASE_SESSION_EXPIRE

# Web Database Keys

# web.session:session_id : {
#   bird: ""
#   media_type: ""
#   answered: 1
#   prevB: ""
#   prevJ: 20
#   tempScore: 0
#   user_id: 0
# }

# web.user:user_id : {
#   avatar_hash: ""
#   avatar_url: "https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
#   username: ""
#   discriminator: ""
# }


def web_session_setup(session_id):
    logger.info("setting up session")
    session_id = str(session_id)
    if database.exists(f"web.session:{session_id}"):
        logger.info("session data ok")
    else:
        database.hset(
            f"web.session:{session_id}",
            mapping={
                "bird": "",
                "media_type": "",
                "answered": 1,  # true = 1, false = 0
                "prevB": "",
                "prevJ": 20,
                "tempScore": 0,  # not used = -1
                "user_id": 0,  # not set = 0
            },
        )
        database.expire(f"web.session:{session_id}", DATABASE_SESSION_EXPIRE)
        logger.info("session set up")


def update_web_user(user_data):
    logger.info("updating user data")
    session_id = get_session_id()
    user_id = str(user_data["id"])
    database.hset(f"web.session:{session_id}", "user_id", user_id)
    database.expire(f"web.session:{session_id}", DATABASE_SESSION_EXPIRE)
    database.hset(
        f"web.user:{user_id}",
        mapping={
            "avatar_hash": str(user_data["avatar"]),
            "avatar_url": f"https://cdn.discordapp.com/avatars/{user_id}/{user_data['avatar']}.png",
            "username": str(user_data["username"]),
            "discriminator": str(user_data["discriminator"]),
        },
    )
    asyncio.run(user_setup(user_id))
    tempScore = int(database.hget(f"web.session:{session_id}", "tempScore"))
    if tempScore not in (0, -1):
        database.zincrby("users:global", tempScore, int(user_id))
        database.hset(f"web.session:{session_id}", "tempScore", -1)
    logger.info("updated user data")


def get_session_id():
    if "id" not in session:
        session["id"] = start_session()
        return str(session["id"])
    if not verify_session(session["id"]):
        session["id"] = start_session()
        return str(session["id"])
    return str(session["id"])


def start_session():
    logger.info("creating session id")
    session_id = 0
    session_id = random.randint(420000000, 420999999)
    while database.exists(f"web.session:{session_id}") and session_id == 0:
        session_id = random.randint(420000000, 420999999)
    logger.info(f"session_id: {session_id}")
    web_session_setup(session_id)
    logger.info(f"created session id: {session_id}")
    return session_id


def verify_session(session_id):
    session_id = str(session_id)
    logger.info(f"verifying session id: {session_id}")
    if not database.exists(f"web.session:{session_id}"):
        logger.info("doesn't exist")
        return False
    if int(database.hget(f"web.session:{session_id}", "user_id")) == 0:
        logger.info("exists, no user id")
        return True
    logger.info("exists with user id")
    return int(database.hget(f"web.session:{session_id}", "user_id"))
