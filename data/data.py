# data.py | import data from lists
# Copyright (C) 2019  EraserBird, person_v1.32, hmmm

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

import os

import redis
# Import modules for other files
from discord.ext import commands

# define database for one connection
database = redis.from_url(os.getenv("REDIS_URL"))

# Database Format Definitions

# prevJ - makes sure it sends a diff image
# prevB - makes sure it sends a diff bird
# prevS - makes sure it sends a diff song

# server format = {
# ctx.channel.id : [bird, answered, songbird, songanswered,
#                     totalCorrect, goatsucker, goatsuckeranswered,
#                     prevJ, prevB, "prevS"]
# }

# user format = {
# "user":[userid, #ofcorrect]
# }

# incorrect birds format = {
# "incorrect":[bird name, #incorrect]
# }


class GenericError(commands.CommandError):
    def __init__(self, message=None):
        super().__init__(message=message)


# Lists of birds, memes, and other info


goatsuckers = ["Common Pauraque", "Chuck-will's-widow", "Whip-poor-will"]
sciGoat = ["Nyctidromus albicollis", "Antrostomus carolinensis", "Antrostomus vociferus"]

def _main():
    filenames = ("birdList", "sciBirdList", "memeList", "songBirds", "sciSongBirds")
    # Converts txt file of data into lists
    lists=[]
    for filename in filenames:
        print(f"Working on {filename}")
        with open(f'data/{filename}.txt', 'r') as f:
            lists.append([line.strip() for line in f])
        print("Done!")
    return lists	


birdList,sciBirdList,memeList,songBirds,sciSongBirds=_main() #pylint disable: unbalanced-tuple-unpacking
