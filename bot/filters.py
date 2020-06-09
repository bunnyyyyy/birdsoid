from typing import Union
from collections.abc import Iterable

# Macaulay Library URLs
CATALOG_URL = "https://search.macaulaylibrary.org/catalog.json?searchField=species"
COUNT = 20  # number of media items from catalog url


class Filter:
    _boolean_options = ("small", "bw")

    def __init__(
        self,
        age: Union[str, Iterable] = (),
        sex: Union[str, Iterable] = (),
        behavior: Union[str, Iterable] = (),
        breeding: Union[str, Iterable] = (),
        sounds: Union[str, Iterable] = (),
        tags: Union[str, Iterable] = (),
        captive: Union[str, Iterable] = (),
        quality: Union[str, Iterable] = ("3", "4", "5"),
        small: bool = False,
        bw: bool = False,
    ):
        """Represents Macaulay Library media filters.

        Valid filters:
        - Age:
            - a (adult), i (immature), j (juvenile), u (unknown)
        - Sex:
            - m (male), f (female), u (unknown)
        - Behavior:
            - e (eating/foraging), f (flying), p (preening), vocalizing (vocalizing), molting (molting)
        - Breeding:
            - fy (feeding young), cdc (courtship, display, or copulation)
            - cf (carrying food), cfs (carrying fecal sac), nb (nest building)
        - Sounds:
            - s (song), c (call), nv (non-vocal), ds (dawn song), fs (flight song)
            - fc (flight call), dt (duet), env (environmental), peo (people)
        - Photo Tags:
            - mul (multiple species), in (in-hand), nes (nest), egg (eggs), hab (habitat),
            - wat (watermark), bac (back of camera), dea (dead), fie (field notes/sketch), non (no bird)
        - Captive (animals in captivity):
            - all, yes, no
        - Quality:
            - 0 (unrated), 1 (worst) - 5 (best)
        - Small:
            - True (uses previewUrl), False (uses mediaUrl)
        - Black & White:
            - True (black and white), False (color)
        """
        self.age = age
        self.sex = sex
        self.behavior = behavior
        self.breeding = breeding
        self.sounds = sounds
        self.tags = tags
        self.captive = captive
        self.quality = quality
        self.small = small
        self.bw = bw

        for item in self.__dict__.items():
            if isinstance(item[1], str):
                cleaned = set(item[1].split(" "))
                cleaned.discard("")
                self.__dict__[item[0]] = cleaned
            elif isinstance(item[1], Iterable):
                cleaned = set(item[1])
                cleaned.discard("")
                self.__dict__[item[0]] = cleaned
        self._validate()

    def __repr__(self):
        return self.__dict__.__repr__()

    def _clear(self):
        """Clear all filters."""
        self.__dict__ = {
            k: (False if k in self._boolean_options else set())
            for k in self.__dict__.keys()
        }

    def _validate(self) -> bool:
        """Check the validity of filter values.

        Return True if filter values are valid.
        Raises a ValueError if filter values are invalid.
        Raises a TypeError if values are not iterables.
        """
        valid_values = {
            "age": {"a", "i", "j", "u"},
            "sex": {"m", "f", "u"},
            "behavior": {"e", "f", "p", "vocalizing", "molting"},
            "breeding": {"cdc", "fy", "cf", "cfs", "nb"},
            "sounds": {"s", "c", "nv", "ds", "fs", "fc", "dt", "env", "peo"},
            "tags": {
                "mul",
                "in",
                "nes",
                "egg",
                "hab",
                "wat",
                "bac",
                "dea",
                "fie",
                "non",
            },
            "captive": {"all", "yes", "no"},
            "quality": {"0", "1", "2", "3", "4", "5"},
            "small": {True, False},
        }
        for item in self.__dict__.items():
            if item[0] in self._boolean_options:
                if not isinstance(item[1], bool):
                    raise TypeError(f"{item[0]} is not a boolean.")
                continue
            if not isinstance(item[1], Iterable):
                raise TypeError(f"{item[0]} is not an iterable.")
            if not set(item[1]).issubset(valid_values[item[0]]):
                raise ValueError(f"{item[1]} contains invalid {item[0]} values.")
        return True

    def url(self, taxon_code: str, media_type: str) -> str:
        """Generate the search url based on the filters.
        
        `media_type` is all, p (pictures), a (audio), v (video)
        """
        self._validate()
        url_parameter_names = {
            "age": "&age={}",
            "sex": "&sex={}",
            "behavior": "&beh={}",
            "breeding": "&bre={}",
            "sounds": "&behaviors={}",
            "tags": "&tag={}",
            "captive": "&cap={}",
            "quality": "&qua={}",
        }
        url = CATALOG_URL
        url += f"&taxonCode={taxon_code}&mediaType={media_type}&count={COUNT}"

        for item in self.__dict__.items():
            if (
                (item[0] == "sounds" and media_type == "p")
                or (item[0] == "tags" and media_type == "a")
                or item[0] in self._boolean_options
            ):
                # disable invalid filters on certain media types
                continue
            for value in item[1]:
                if value in ("env", "peo") and item[0] == "sounds":
                    # two sound filters have 'tag' as the url parameter
                    url += url_parameter_names["tags"].format(value)
                else:
                    url += url_parameter_names[item[0]].format(value)
        return url

    def to_int(self):
        """Convert filters into an integer representation.
        
        This is calculated with a 47 digit binary number representing the 47 filter options.
        """
        out = ["0"] * 47
        indexes = self.aliases(num=True)
        for title, filters in self.__dict__.items():
            if title in self._boolean_options:
                if filters:
                    out[indexes[title][filters] - 1] = "1"
                continue
            for name in filters:
                out[indexes[title][name] - 1] = "1"
        return int("".join(reversed(out)), 2)

    def from_int(self, number: int):
        """Convert an int to a filter object."""
        if number >= 2 ** 47 or number < 0:
            raise ValueError("Input number out of bounds.")

        self._clear()  # reset existing filters to empty
        binary = reversed("{0:0>47b}".format(number))
        lookup = self.aliases(lookup=True)
        for index, value in enumerate(binary):
            if int(value):
                key = lookup[str(index + 1)]
                if key[0] in self._boolean_options:
                    self.__dict__[key[0]] = key[1]
                    continue
                self.__dict__[key[0]].add(key[1])
        return self

    def __xor__(self, number: int):
        self.xor(number)

    def xor(self, number: int):
        """Combine/toggle filters by xor-ing the integer representations."""
        if number >= 2 ** 47 or number < 0:
            raise ValueError("Input number out of bounds.")
        self.from_int(number ^ self.to_int())

    def parse(self, args: str):
        """Parse an argument string as Macaulay Library media filters."""
        self.__init__()  # reset existing filters to default
        lookup = self.aliases(lookup=True)
        args = args.lower().strip()
        if "," in args:
            args = map(lambda x: x.strip(), args.split(","))
        else:
            args = map(lambda x: x.strip(), args.split(" "))

        for arg in args:
            key = lookup.get(arg)
            if key is not None:
                if key[0] in self._boolean_options:
                    self.__dict__[key[0]] = key[1]
                    continue
                self.__dict__[key[0]].add(key[1])
        return self

    def display(self):
        """Return a list describing the filters."""
        output = []
        display = self.aliases(display_lookup=True)
        for title, values in self.__dict__.items():
            if title in self._boolean_options:
                if values:
                    output.append(f"{title}: {display[title][1][values]}")
                continue
            for name in values:
                output.append(f"{title}: {display[title][1][name]}")
        return output

    def aliases(
        self, lookup: bool = False, num: bool = False, display_lookup: bool = False
    ):
        """Generate filter alises.

        If lookup, returns a dict mapping aliases to filter names,
        elif num, returns a dict mapping filter names to numbers,
        elif display_lookup, returns a dict mapping internal names to display names,
        else returns a display text.
        """
        # the keys of this dict are in the form ("display text", "internal key")
        # the first alias should be a number
        aliases = {
            ("age", "age"): {
                ("adult", "a"): ("1", "adult", "a"),
                ("immature", "i"): ("2", "immature", "i"),
                ("juvenile", "j"): ("3", "juvenile", "j"),
                ("unknown", "u"): ("4", "age:unknown", "unknown age"),
            },
            ("sex", "sex"): {
                ("male", "m"): ("5", "male", "m"),
                ("female", "f"): ("6", "female", "f"),
                ("unknown", "u"): ("7", "sex:unknown", "unknown sex"),
            },
            ("behavior", "behavior"): {
                ("eating/foraging", "ef"): ("8", "eating", "foraging", "e", "ef"),
                ("flying", "f"): ("9", "flying", "fly"),
                ("preening", "p"): ("10", "preening", "p"),
                ("vocalizing", "vocalizing"): ("11", "vocalizing", "vo"),
                ("molting", "molting"): ("12", "molting", "mo"),
            },
            ("breeding", "breeding"): {
                ("courtship, display, or copulation", "cdc"): (
                    "13",
                    "courtship",
                    "display",
                    "copulation",
                    "cdc",
                ),
                ("feeding young", "fy"): ("14", "feeding", "feeding young", "fy"),
                ("carrying food", "cf"): ("15", "food", "carrying food", "cf"),
                ("carrying fecal sac", "cfs"): (
                    "16",
                    "fecal",
                    "carrying fecal sac",
                    "fecal sac",
                    "cfs",
                ),
                ("nest building", "nb"): (
                    "17",
                    "nest",
                    "building",
                    "nest building",
                    "nb",
                ),
            },
            ("sounds", "sounds"): {
                ("song", "s"): ("18", "song", "s"),
                ("call", "c"): ("19", "call", "c"),
                ("non-vocal", "nv"): ("20", "non-vocal", "non vocal", "nv"),
                ("dawn song", "ds"): ("21", "dawn", "dawn song", "ds"),
                ("flight song", "fs"): ("22", "flight song", "fs"),
                ("flight call", "fc"): ("23", "flight call", "fc"),
                ("duet", "dt"): ("24", "duet", "dt"),
                ("environmental", "env"): ("25", "environmental", "env"),
                ("people", "peo"): ("26", "people", "peo"),
            },
            ("photo tags", "tags"): {
                ("multiple species", "mul"): (
                    "27",
                    "multiple",
                    "species",
                    "multiple species",
                    "mul",
                ),
                ("in-hand", "in"): ("28", "in-hand", "in hand"),
                ("nest", "nes"): ("29", "nest", "nes"),
                ("eggs", "eff"): ("30", "egg", "eggs"),
                ("habitat", "hab"): ("31", "habitat", "hab"),
                ("watermark", "wat"): ("32", "watermark", "wat"),
                ("back of camera", "bac"): (
                    "33",
                    "back of camera",
                    "camera",
                    "back",
                    "bac",
                ),
                ("dead", "dea"): ("34", "dead", "dea"),
                ("field notes/sketch", "fie"): (
                    "35",
                    "field",
                    "field notes",
                    "sketch",
                ),
                ("no bird", "non"): ("36", "none", "no bird", "non"),
            },
            ("captive (animals in captivity)", "captive"): {
                ("all", "all"): ("37", "captive:all"),
                ("yes", "yes"): ("38", "captive"),
                ("no", "no"): ("39", "captive:no", "not captive"),
            },
            ("quality (defaults to 3,4,5)", "quality"): {
                ("no rating", "0"): ("40", "no rating", "q0"),
                ("terrible", "1"): ("41", "terrible", "q1"),
                ("poor", "2"): ("42", "poor", "q2"),
                ("average", "3"): ("43", "average", "avg", "q3"),
                ("good", "4"): ("44", "good", "q4"),
                ("excellent", "5"): ("45", "excellent", "best", "q5"),
            },
            ("smaller images (defaults to no)", "small"): {
                ("yes", True): ("46", "small", "smaller images"),
            },
            ("black & white (defaults to no)", "bw"): {
                ("yes", True): ("47", "bw", "b&w"),
            },
        }
        if lookup:
            return {
                alias: (title[1], name[1])
                for title, subdict in aliases.items()
                for name, aliases in subdict.items()
                for alias in aliases
            }
        elif num:
            return {
                title[1]: {
                    name[1]: int(aliases[0]) for name, aliases in subdict.items()
                }
                for title, subdict in aliases.items()
            }
        elif display_lookup:
            return {
                title[1]: (title[0], {key[1]: key[0] for key in subdict.keys()})
                for title, subdict in aliases.items()
            }
        else:
            return {
                title[0]: {name[0]: aliases for name, aliases in subdict.items()}
                for title, subdict in aliases.items()
            }
