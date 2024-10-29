from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from agixtsdk import AGiXTSDK
from Extensions import Extensions
from Globals import getenv
import json
import time

try:
    from pycraft.client import Client
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pycraft"])
    from pycraft.client import Client


from pycraft.authentication import AuthenticationToken
from pycraft.exceptions import YggdrasilError


@dataclass
class Block:
    name: str
    x: int
    y: int
    z: int
    properties: Optional[Dict[str, Any]] = None


@dataclass
class Structure:
    name: str
    blocks: List[Block]
    origin: Tuple[int, int, int] = (0, 0, 0)
    offset: int = 0


class Direction(Enum):
    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3


STRUCTURES = [
    {
        "name": "dirt_shelter",
        "offset": -2,
        "blocks": [
            [
                ["", "", "", "", ""],
                ["", "dirt", "dirt", "dirt", ""],
                ["", "dirt", "dirt", "dirt", ""],
                ["", "dirt", "dirt", "dirt", ""],
                ["", "", "dirt", "", ""],
                ["", "", "dirt", "", ""],
            ],
            [
                ["dirt", "dirt", "dirt", "dirt", "dirt"],
                ["dirt", "chest", "bed", "air", "dirt"],
                ["dirt", "air", "bed", "air", "dirt"],
                ["dirt", "air", "air", "air", "dirt"],
                ["dirt", "dirt", "door", "dirt", "dirt"],
                ["dirt", "dirt", "air", "dirt", "dirt"],
            ],
            [
                ["dirt", "dirt", "dirt", "dirt", "dirt"],
                ["dirt", "air", "air", "air", "dirt"],
                ["dirt", "torch", "air", "air", "dirt"],
                ["dirt", "air", "air", "air", "dirt"],
                ["dirt", "dirt", "door", "dirt", "dirt"],
                ["air", "air", "air", "air", "air"],
            ],
            [
                ["air", "air", "air", "air", "air"],
                ["dirt", "dirt", "dirt", "dirt", "dirt"],
                ["dirt", "dirt", "dirt", "dirt", "dirt"],
                ["dirt", "dirt", "dirt", "dirt", "dirt"],
                ["air", "air", "air", "air", "air"],
                ["air", "air", "air", "air", "air"],
            ],
        ],
    },
    {
        "name": "large_house",
        "offset": -4,
        "blocks": [
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "torch",
                    "air",
                    "air",
                    "air",
                    "torch",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "planks",
                    "torch",
                    "air",
                    "air",
                    "air",
                    "torch",
                    "air",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                    "",
                    "",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "air",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "dirt",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "air",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "air",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "",
                ],
            ],
            [
                ["", "", "", "log", "planks", "planks", "planks", "log", "", "", ""],
                [
                    "",
                    "",
                    "",
                    "planks",
                    "furnace",
                    "air",
                    "crafting_table",
                    "planks",
                    "",
                    "",
                    "",
                ],
                ["", "", "", "planks", "air", "air", "air", "planks", "", "", ""],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "air",
                    "planks",
                    "log",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "door",
                    "air",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "air",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                ["", "", "", "planks", "air", "air", "air", "", "air", "planks", ""],
                ["", "", "", "planks", "chest", "air", "air", "bed", "", "planks", ""],
                ["", "", "", "planks", "chest", "air", "air", "", "air", "planks", ""],
                [
                    "",
                    "",
                    "",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
            ],
            [
                ["", "", "", "log", "planks", "planks", "planks", "log", "", "", ""],
                ["", "", "", "planks", "air", "air", "air", "glass", "", "", ""],
                ["", "", "", "planks", "air", "air", "air", "glass", "", "", ""],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "air",
                    "planks",
                    "log",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "door",
                    "air",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "air",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                ["", "", "", "planks", "air", "air", "air", "air", "air", "planks", ""],
                ["", "", "", "planks", "air", "air", "air", "air", "air", "planks", ""],
                ["", "", "", "planks", "air", "air", "air", "air", "air", "planks", ""],
                [
                    "",
                    "",
                    "",
                    "log",
                    "planks",
                    "glass",
                    "glass",
                    "glass",
                    "planks",
                    "log",
                    "",
                ],
            ],
            [
                ["", "", "", "log", "planks", "planks", "planks", "log", "", "", ""],
                ["", "", "", "planks", "air", "air", "air", "glass", "", "", ""],
                ["", "", "", "planks", "torch", "air", "torch", "glass", "", "", ""],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "air",
                    "planks",
                    "log",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "torch",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "torch",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "torch",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "planks",
                    "air",
                    "torch",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "air",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "planks",
                    "air",
                    "torch",
                    "air",
                    "torch",
                    "air",
                    "planks",
                    "",
                ],
                ["", "", "", "planks", "air", "air", "air", "air", "air", "planks", ""],
                ["", "", "", "planks", "air", "air", "air", "air", "air", "planks", ""],
                [
                    "",
                    "",
                    "",
                    "log",
                    "planks",
                    "glass",
                    "glass",
                    "glass",
                    "planks",
                    "log",
                    "",
                ],
            ],
            [
                ["", "", "", "log", "log", "log", "log", "log", "", "", ""],
                ["", "", "", "log", "planks", "planks", "planks", "log", "", "", ""],
                ["", "", "", "log", "planks", "planks", "planks", "log", "", "", ""],
                [
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "",
                ],
                [
                    "log",
                    "air",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "air",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "air",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                ["", "", "", "log", "log", "log", "log", "log", "log", "log", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "planks", "planks", "planks", "", "", "", ""],
                ["", "", "", "", "planks", "planks", "planks", "", "", "", ""],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "bookshelf",
                    "bookshelf",
                    "air",
                    "air",
                    "air",
                    "air",
                    "torch",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "planks",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "torch",
                    "planks",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "log",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "bookshelf",
                    "bookshelf",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "planks",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "log",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "log",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "torch",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "glass",
                    "air",
                    "air",
                    "torch",
                    "air",
                    "air",
                    "air",
                    "air",
                    "air",
                    "glass",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "glass",
                    "log",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "planks",
                    "planks",
                    "log",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "log",
                    "",
                ],
                [
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "log",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "planks",
                    "",
                    "",
                ],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
            [
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "planks", "planks", "planks", "", "", ""],
                ["", "", "", "", "", "planks", "planks", "planks", "", "", ""],
                ["", "", "", "", "", "planks", "planks", "planks", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", "", ""],
            ],
        ],
    },
    {
        "name": "small_stone_house",
        "offset": -1,
        "blocks": [
            [
                ["", "", "", "", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "", "planks", "", ""],
                ["", "", "", "", ""],
            ],
            [
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                ],
                ["cobblestone", "chest", "bed", "air", "cobblestone"],
                ["cobblestone", "air", "bed", "air", "cobblestone"],
                ["cobblestone", "air", "air", "air", "cobblestone"],
                ["cobblestone", "air", "air", "air", "cobblestone"],
                ["cobblestone", "cobblestone", "door", "cobblestone", "cobblestone"],
                ["", "air", "air", "air", ""],
            ],
            [
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                ],
                ["cobblestone", "torch", "air", "torch", "cobblestone"],
                ["cobblestone", "air", "air", "air", "cobblestone"],
                ["cobblestone", "air", "air", "air", "cobblestone"],
                ["cobblestone", "torch", "air", "torch", "cobblestone"],
                ["cobblestone", "cobblestone", "door", "cobblestone", "cobblestone"],
                ["", "air", "air", "air", ""],
            ],
            [
                ["air", "air", "air", "air", "air"],
                ["air", "cobblestone", "cobblestone", "cobblestone", "air"],
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                ],
                [
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                    "cobblestone",
                ],
                ["air", "cobblestone", "cobblestone", "cobblestone", "air"],
                ["air", "air", "air", "air", "air"],
                ["", "air", "air", "air", ""],
            ],
        ],
    },
    {
        "name": "small_wood_house",
        "offset": -1,
        "blocks": [
            [
                ["", "", "", "", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "planks", "planks", "planks", ""],
                ["", "", "planks", "", ""],
                ["", "", "", "", ""],
            ],
            [
                ["log", "planks", "planks", "planks", "log"],
                ["planks", "chest", "bed", "air", "planks"],
                ["planks", "air", "bed", "air", "planks"],
                ["planks", "air", "air", "air", "planks"],
                ["planks", "air", "air", "air", "planks"],
                ["log", "planks", "door", "planks", "log"],
                ["", "air", "air", "air", ""],
            ],
            [
                ["log", "planks", "planks", "planks", "log"],
                ["planks", "torch", "air", "torch", "planks"],
                ["planks", "air", "air", "air", "planks"],
                ["planks", "air", "air", "air", "planks"],
                ["planks", "torch", "air", "torch", "planks"],
                ["log", "planks", "door", "planks", "log"],
                ["", "air", "air", "air", ""],
            ],
            [
                ["air", "air", "air", "air", "air"],
                ["air", "planks", "planks", "planks", "air"],
                ["planks", "planks", "planks", "planks", "planks"],
                ["planks", "planks", "planks", "planks", "planks"],
                ["air", "planks", "planks", "planks", "air"],
                ["air", "air", "air", "air", "air"],
                ["", "air", "air", "air", ""],
            ],
        ],
    },
]

BUILDING_EXAMPLES = """
Here are examples of how to interpret building requests:

User: "build a dirt house"
Response: {
    "type": "house",
    "style": "dirt",
    "size": "small",
    "features": ["door", "windows", "bed", "chest", "torch"],
    "template_match": "dirt_shelter"
}

User: "make me a wooden cabin"
Response: {
    "type": "house",
    "style": "wood",
    "size": "small", 
    "features": ["door", "windows", "bed", "crafting_table", "chest", "torch"],
    "template_match": "small_wood_house"
}
"""


class minecraft(Extensions):
    def __init__(
        self,
        MINECRAFT_USERNAME: str = "",
        MINECRAFT_PASSWORD: str = "",
        MINECRAFT_SERVER: str = "your-server-hostname.com:19132",
        **kwargs,
    ):
        self.username = MINECRAFT_USERNAME
        self.password = MINECRAFT_PASSWORD
        self.host = MINECRAFT_SERVER.split(":")[0]
        try:
            self.port = int(MINECRAFT_SERVER.split(":")[1])
        except:
            self.port = 19132

        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )

        self.structure_templates = self._load_structures()
        self.client = None
        self.failures = 0

        self.commands = {
            "Build Minecraft Structure": self.build_structure,
            "Place Minecraft Block": self.place_block,
        }

    def _load_structures(self) -> Dict[str, Structure]:
        """Load predefined structure templates from JSON files"""
        global STRUCTURES
        structures = {}
        for data in STRUCTURES:
            blocks = []
            for y, layer in enumerate(data["blocks"]):
                for z, row in enumerate(layer):
                    for x, block_name in enumerate(row):
                        if block_name and block_name != "air":
                            blocks.append(
                                Block(
                                    name=block_name,
                                    x=x,
                                    y=y + data.get("offset", 0),
                                    z=z,
                                )
                            )
            structures[data["name"]] = Structure(
                name=data["name"], blocks=blocks, offset=data.get("offset", 0)
            )
        return structures

    async def connect(self) -> bool:
        """Connect to a Minecraft server"""
        if self.host == "your-server-hostname.com":
            print("Minecraft server not configured")
            return False
        try:
            if self.password:
                await self._authenticate()

            self.client = Client(
                host=self.host,
                port=self.port,
                username=self.username,
                auth_token=self.auth_token,
            )
            await self.client.connect()
            await self.client.wait_for_spawn()
            self.failures = 0
            return True
        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                time.sleep(5)
                return await self.connect()
            return False

    async def disconnect(self):
        """Disconnect from the Minecraft server"""
        if self.client:
            await self.client.disconnect()

    async def _authenticate(self):
        """Handle Microsoft/Xbox Live authentication"""
        try:
            try:
                with open(f".auth-{self.username}.json") as f:
                    auth_data = json.load(f)
                    self.auth_token = AuthenticationToken(
                        access_token=auth_data["access_token"],
                        client_token=auth_data["client_token"],
                    )
                if not await self.auth_token.validate():
                    raise Exception("Invalid cached token")
            except (FileNotFoundError, Exception):
                self.auth_token = AuthenticationToken(
                    username=self.username, password=self.password
                )
                await self.auth_token.authenticate()
                with open(f".auth-{self.username}.json", "w") as f:
                    json.dump(
                        {
                            "access_token": self.auth_token.access_token,
                            "client_token": self.auth_token.client_token,
                        },
                        f,
                    )
        except YggdrasilError as e:
            print(f"Authentication failed: {e}")
            raise

    async def get_player_position(self) -> Tuple[int, int, int]:
        """Get the player's current position"""
        if not self.client:
            raise ConnectionError("Not connected to server")
        pos = self.client.position
        return (int(pos.x), int(pos.y), int(pos.z))

    async def get_height(self, x: int, z: int) -> int:
        """Get the height of the world at the given x,z coordinates"""
        if not self.client:
            raise ConnectionError("Not connected to server")
        start_y = 320
        for y in range(start_y, -64, -1):
            block = await self.get_block(x, y, z)
            if block and block.type != "air":
                return y + 1
        return 0

    async def get_block(self, x: int, y: int, z: int) -> Optional[Block]:
        """Get information about the block at the given coordinates"""
        if not self.client:
            raise ConnectionError("Not connected to server")
        try:
            block_data = await self.client.get_block(x, y, z)
            if block_data:
                return Block(
                    name=block_data.id,
                    x=x,
                    y=y,
                    z=z,
                    properties=(
                        block_data.properties
                        if hasattr(block_data, "properties")
                        else None
                    ),
                )
            return None
        except Exception as e:
            print(f"Failed to get block at ({x}, {y}, {z}): {e}")
            return None

    async def place_block(
        self, block_type: str, x: int, y: int, z: int, properties: Optional[Dict] = None
    ):
        """Place a block at the given coordinates"""
        if not self.client:
            raise ConnectionError("Not connected to server")
        try:
            existing = await self.get_block(x, y, z)
            if existing and existing.type != "air":
                await self.break_block(x, y, z)
            await self.client.place_block(
                position=(x, y, z), block_type=block_type, properties=properties
            )
            new_block = await self.get_block(x, y, z)
            if not new_block or new_block.name != block_type:
                raise Exception(f"Failed to place {block_type} at ({x}, {y}, {z})")
        except Exception as e:
            print(f"Failed to place block: {e}")
            raise

    async def break_block(self, x: int, y: int, z: int):
        """Break the block at the given coordinates"""
        if not self.client:
            raise ConnectionError("Not connected to server")
        try:
            await self.client.break_block((x, y, z))
            block = await self.get_block(x, y, z)
            if block and block.name != "air":
                raise Exception(f"Failed to break block at ({x}, {y}, {z})")
        except Exception as e:
            print(f"Failed to break block: {e}")
            raise

    async def build_structure(self, structure_description: str) -> bool:
        """Main pipeline for structure creation"""
        try:
            if not self.client:
                await self.connect()

            structure_plan = await self._get_structure_plan(structure_description)
            print(f"Generated building plan: {structure_plan}")

            if not structure_plan.get("template_match"):
                structure = await self._generate_structure(structure_plan)
                print("Generated custom structure")
            else:
                structure = self.structure_templates[structure_plan["template_match"]]
                print(f"Using template: {structure_plan['template_match']}")

            if not structure or not self.validate_structure(structure):
                print("Structure validation failed")
                return False

            location = await self._find_build_location(structure)
            if not location:
                print("Could not find suitable build location")
                return False

            adapted_structure = await self._adapt_to_terrain(structure, location)
            success = await self._execute_build(adapted_structure, location)

            return success

        except Exception as e:
            print(f"Build failed with error: {e}")
            return False

    async def _get_structure_plan(self, request: str) -> Dict:
        """Get LLM to interpret build request into actionable plan"""
        context = f"## Minecraft Building Examples\n\n{BUILDING_EXAMPLES}"
        prompt = f"""Please analyze this Minecraft build request and provide a structured building plan.
Use the Minecraft Build Examples as a guide for your response.

Request: "{request}"
        
Provide a similar JSON response for the current request in the answer block.
Consider available templates: {list(self.structure_templates.keys())}
Only suggest a template_match if it exactly matches the request needs."""

        response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={"context": context, "user_input": prompt},
        )

        # Extract JSON from response
        if "```json" in response:
            response = response.split("```json")[1]
        if "```" in response:
            response = response.split("```")[0]
        return json.loads(response)

    def validate_structure(self, structure: Structure) -> bool:
        """Validate structure before attempting to build"""
        if not structure.blocks:
            return False

        has_floor = any(b.y == 0 for b in structure.blocks)
        has_walls = any(b.y > 0 for b in structure.blocks)

        return has_floor and has_walls

    async def _find_build_location(
        self, structure: Structure
    ) -> Optional[Tuple[int, int, int]]:
        """Find suitable flat area for structure"""
        player_pos = await self.get_player_position()
        x, y, z = player_pos

        max_x = max(b.x for b in structure.blocks)
        max_z = max(b.z for b in structure.blocks)

        for radius in range(1, 11):
            for test_x in range(x - radius, x + radius + 1):
                for test_z in range(z - radius, z + radius + 1):
                    if abs(test_x - x) != radius and abs(test_z - z) != radius:
                        continue

                    if await self._is_area_suitable(test_x, y, test_z, max_x, max_z):
                        try:
                            test_structure = await self._adapt_to_terrain(
                                structure, (test_x, y, test_z)
                            )
                            if self.validate_structure(test_structure):
                                return (test_x, y, test_z)
                        except Exception:
                            continue
        return None

    async def _is_area_suitable(
        self, x: int, y: int, z: int, width: int, depth: int
    ) -> bool:
        """Check if area is suitable for building"""
        heights = []
        blocks = []

        for dx in range(width + 1):
            for dz in range(depth + 1):
                height = await self.get_height(x + dx, z + dz)
                heights.append(height)

                for dy in range(height, height + 10):
                    block = await self.get_block(x + dx, dy, z + dz)
                    if block and block.name not in [
                        "air",
                        "grass",
                        "tall_grass",
                        "snow",
                    ]:
                        blocks.append(block)

        height_variation = max(heights) - min(heights)
        has_obstacles = len(blocks) > 0
        lowest_block = await self.get_block(x, min(heights), z)
        over_liquid = lowest_block and lowest_block.name in ["water", "lava"]

        return height_variation <= 2 and not has_obstacles and not over_liquid

    async def _adapt_to_terrain(
        self, structure: Structure, location: Tuple[int, int, int]
    ) -> Structure:
        """Modify structure to better fit terrain"""
        x, y, z = location
        adjusted_blocks = []
        heights = {}

        for block in structure.blocks:
            world_x = x + block.x
            world_z = z + block.z
            if (world_x, world_z) not in heights:
                heights[(world_x, world_z)] = await self.get_height(world_x, world_z)

        base_height = min(heights.values())
        for block in structure.blocks:
            world_x = x + block.x
            world_z = z + block.z
            height_diff = heights[(world_x, world_z)] - base_height

            adjusted_blocks.append(
                Block(
                    name=block.name,
                    x=block.x,
                    y=block.y + height_diff,
                    z=block.z,
                    properties=block.properties,
                )
            )

        return Structure(
            name=structure.name,
            blocks=adjusted_blocks,
            origin=structure.origin,
            offset=structure.offset,
        )

    async def _execute_build(
        self, structure: Structure, location: Tuple[int, int, int]
    ) -> bool:
        """Execute the building of a structure"""
        start_x, start_y, start_z = location
        failed_blocks = []

        try:
            for block in structure.blocks:
                world_x = start_x + block.x
                world_y = start_y + block.y
                world_z = start_z + block.z

                try:
                    await self.place_block(
                        block.name, world_x, world_y, world_z, block.properties
                    )
                except Exception as e:
                    print(
                        f"Failed to place {block.name} at ({world_x}, {world_y}, {world_z}): {e}"
                    )
                    failed_blocks.append((block, (world_x, world_y, world_z)))
                    continue

            if failed_blocks:
                # Try to fix failed blocks
                for block, pos in failed_blocks:
                    try:
                        time.sleep(1)
                        await self.place_block(
                            block.name, pos[0], pos[1], pos[2], block.properties
                        )
                        failed_blocks.remove((block, pos))
                    except Exception as e:
                        print(f"Second attempt failed for {block.name} at {pos}: {e}")

            return len(failed_blocks) == 0

        except Exception as e:
            print(f"Build failed catastrophically: {e}")
            return False

    async def _generate_structure(self, plan: Dict) -> Optional[Structure]:
        """Generate a new structure based on the plan using LLM"""
        context = """The code should return a list of blocks to place relative to a starting position.

Example building patterns:
```python
# Build foundation
for x in range(width):
    for z in range(depth):
        place_block("stone", start_x + x, start_y, start_z + z)

# Build walls
for y in range(height):
    for x in range(width):
        for z in range(depth):
            if x in (0, width-1) or z in (0, depth-1):
                place_block("planks", start_x + x, start_y + y, start_z + z)

# Add roof
for x in range(width):
    for z in range(depth):
        place_block("planks", start_x + x, start_y + height, start_z + z)
```"""

        prompt = f"""Generate Python code to build a Minecraft structure with these specifications:
{json.dumps(plan, indent=2)}

- Generate code that creates a structure matching the specifications.
- Each block should have: name, x, y, z coordinates.
- Return a list of blocks to place relative to a starting position.
- Use only valid Minecraft block types.
Return only the Python code in the answer block."""

        code_response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={"user_input": prompt, "context": context},
        )
        place_block_code = f"""from agixtsdk import AGiXTSDK

def place_block(block_type, x, y, z, properties=None):
    agixt = AGiXTSDK(base_uri="{self.ApiClient.base_uri}", api_key="{self.api_key}")
    return agixt.execute_command(
        agent_name="{self.agent_name}",
        command_name="Place Minecraft Block",
        command_args={{"block_type": block_type, "x": x, "y": y, "z": z, "properties": properties}},
    )
"""
        code_response = str(code_response).strip()
        if "```python" in code_response:
            code_response = code_response.split("```python")[1]
        if "```" in code_response:
            code_response = code_response.split("```")[0]
        code_response = code_response.strip()
        code_response = f"{place_block_code}\n\n{code_response}"
        try:
            # Execute the generated code in a safe environment
            response = self.ApiClient.execute_command(
                agent_name=self.agent_name,
                command_name="Execute Python Code",
                command_args={"code": code_response},
            )

            try:
                namespace = json.loads(response)
            except:
                print(f"Failed to parse response from JSON: {response}")
                namespace = {}

            blocks = namespace.get("blocks", [])

            return Structure(
                name=f"{plan['type']}_{plan['style']}",
                blocks=[Block(**b) for b in blocks],
            )

        except Exception as e:
            print(f"Failed to generate structure: {e}")
            # Fallback to simple shelter
            return self.structure_templates.get("dirt_shelter")
