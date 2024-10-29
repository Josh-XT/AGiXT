from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from agixtsdk import AGiXTSDK
from Extensions import Extensions
from Globals import getenv
import json

try:
    from mcipc.rcon.be import Client as BedrockClient
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "mcipc"])
    from mcipc.rcon.be import Client as BedrockClient


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
        MINECRAFT_PASSWORD: str = "",
        MINECRAFT_SERVER: str = "your-server-hostname.com:19132",
        MINECRAFT_PLAYER_NAME: str = "Your-Player-Name",
        **kwargs,
    ):
        # Minecraft password is the RCON password for the server
        self.password = MINECRAFT_PASSWORD
        self.host = MINECRAFT_SERVER.split(":")[0]
        self.player_name = MINECRAFT_PLAYER_NAME
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
        """Load predefined structure templates from the STRUCTURES data"""
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

    def connect(self) -> bool:
        """Connect to the Minecraft server via RCON"""
        try:
            self.client = BedrockClient(self.host, self.port, passwd=self.password)
            self.client.connect()
            return True
        except Exception as e:
            print(f"Failed to connect via RCON: {e}")
            return False

    def disconnect(self):
        """Disconnect from the Minecraft server"""
        if self.client:
            self.client.disconnect()
            self.client = None

    async def get_player_position(self) -> Tuple[int, int, int]:
        """Get the player's current position"""
        if not self.client:
            if not self.connect():
                raise ConnectionError("Not connected to server")

        try:
            # Use the 'querytarget' command to get player data in Bedrock Edition
            command = f"querytarget {self.player_name}"
            response = self.client.command(command)

            if response:
                # The response is a JSON string
                data = json.loads(response)

                # Extract position data
                if "statusCode" in data and data["statusCode"] == 0:
                    position = data["position"]
                    x = position["x"]
                    y = position["y"]
                    z = position["z"]
                    return (int(x), int(y), int(z))
                else:
                    print(
                        f"Failed to get position for player {self.player_name}: {data}"
                    )
                    return (0, 64, 0)  # Default position
            else:
                print(f"No response received when querying player position.")
                return (0, 64, 0)  # Default position
        except Exception as e:
            print(f"Failed to get player position: {e}")
            return (0, 64, 0)  # Default position

    async def get_height(self, x: int, z: int) -> int:
        """Get the height of the world at the given x,z coordinates"""
        if not self.client:
            if not self.connect():
                raise ConnectionError("Not connected to server")
        try:
            # Start from the highest possible Y coordinate
            for y in range(320, -64, -1):
                block = await self.get_block(x, y, z)
                if block and block.name != "air":
                    return y + 1
            return 0  # If no blocks are found, return 0
        except Exception as e:
            print(f"Failed to get height at ({x}, {z}): {e}")
            return 0

    async def get_block(self, x: int, y: int, z: int) -> Optional[Block]:
        """Get information about the block at the given coordinates"""
        if not self.client:
            if not self.connect():
                raise ConnectionError("Not connected to server")
        try:
            # Use the 'testforblock' command to check for a block at the given coordinates
            command = f"testforblock {x} {y} {z} minecraft:air"
            response = self.client.command(command)
            if "Successfully found the block" in response:
                # The block is air
                return Block(name="air", x=x, y=y, z=z)
            else:
                # The block is not air, so we can try other block types
                # Unfortunately, Bedrock Edition RCON does not provide a command to get the exact block type
                # We will return a generic non-air block
                return Block(name="solid_block", x=x, y=y, z=z)
        except Exception as e:
            print(f"Failed to get block at ({x}, {y}, {z}): {e}")
            return None

    async def place_block(
        self, block_type: str, x: int, y: int, z: int, properties: Optional[Dict] = None
    ):
        """Place a block at the given coordinates using RCON"""
        if not self.client:
            if not self.connect():
                raise ConnectionError("Not connected to server")
        try:
            # Construct the command to set the block
            properties_str = ""
            if properties:
                # Convert properties dict to a string format if necessary
                properties_str = (
                    "[" + ",".join(f"{k}={v}" for k, v in properties.items()) + "]"
                )
            command = f'setblock {x} {y} {z} "{block_type}{properties_str}" replace'
            response = self.client.command(command)
            if response and "error" in response.lower():
                print(f"Error placing block: {response}")
        except Exception as e:
            print(f"Failed to place block: {e}")
            raise

    async def break_block(self, x: int, y: int, z: int):
        """Break the block at the given coordinates"""
        if not self.client:
            if not self.connect():
                raise ConnectionError("Not connected to server")
        try:
            # Replace the block with air to simulate breaking it
            command = f"setblock {x} {y} {z} air replace"
            response = self.client.command(command)
            if response and "error" in response.lower():
                print(f"Error breaking block: {response}")
        except Exception as e:
            print(f"Failed to break block: {e}")
            raise

    async def build_structure(self, structure_description: str) -> bool:
        """Main pipeline for structure creation"""
        try:
            if not self.client:
                if not self.connect():
                    return False

            structure_plan = await self._get_structure_plan(structure_description)
            print(f"Generated building plan: {structure_plan}")

            if not structure_plan.get("template_match"):
                structure = await self._generate_structure(structure_plan)
                print("Generated custom structure")
            else:
                structure = self.structure_templates.get(
                    structure_plan["template_match"]
                )
                if not structure:
                    print(f"Template '{structure_plan['template_match']}' not found.")
                    return False
                print(f"Using template: {structure_plan['template_match']}")

            if not structure or not self.validate_structure(structure):
                print("Structure validation failed")
                return False

            # Find a suitable build location near the player
            location = await self._find_build_location(structure)
            if not location:
                print("No suitable build location found.")
                return False

            adapted_structure = self._adapt_to_terrain(structure, location)
            success = await self._execute_build(adapted_structure, location)

            return success

        except Exception as e:
            print(f"Build failed with error: {e}")
            return False

    async def _get_structure_plan(self, request: str) -> Dict:
        """Get LLM to interpret build request into actionable plan"""
        context = f"## Minecraft Building Examples\n\n{BUILDING_EXAMPLES}"
        prompt = f"""Please analyze this Minecraft build request and provide a structured building plan.
Use the Minecraft Building Examples as a guide for your response.

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
        try:
            if "```json" in response:
                response = response.split("```json")[1]
            if "```" in response:
                response = response.split("```")[0]
            return json.loads(response)
        except Exception as e:
            print(f"Failed to parse structure plan: {e}")
            return {}

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

        # Search in a spiral pattern around the player
        for radius in range(0, 20):
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    test_x = x + dx
                    test_z = z + dz
                    if abs(dx) != radius and abs(dz) != radius:
                        continue

                    if await self._is_area_suitable(test_x, y, test_z, max_x, max_z):
                        return (test_x, y, test_z)
        return None

    async def _is_area_suitable(
        self, x: int, y: int, z: int, width: int, depth: int
    ) -> bool:
        """Check if area is suitable for building"""
        heights = []

        for dx in range(width + 1):
            for dz in range(depth + 1):
                height = await self.get_height(x + dx, z + dz)
                heights.append(height)

        height_variation = max(heights) - min(heights)
        return height_variation <= 1

    def _adapt_to_terrain(
        self, structure: Structure, location: Tuple[int, int, int]
    ) -> Structure:
        """Modify structure to better fit terrain"""
        # Adjust the Y-coordinate of the structure based on the terrain height
        start_x, start_y, start_z = location
        adjusted_blocks = []
        min_height = min(block.y for block in structure.blocks)

        for block in structure.blocks:
            adjusted_block = Block(
                name=block.name,
                x=block.x,
                y=block.y - min_height,  # Adjust to start from Y=0
                z=block.z,
                properties=block.properties,
            )
            adjusted_blocks.append(adjusted_block)

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

            return len(failed_blocks) == 0

        except Exception as e:
            print(f"Build failed catastrophically: {e}")
            return False

    async def _generate_structure(self, plan: Dict) -> Optional[Structure]:
        """Generate a new structure based on the plan using LLM"""
        context = """The code should return a list of blocks to place relative to a starting position.

Example building patterns:
```python
blocks = []
# Build foundation
for x in range(width):
    for z in range(depth):
        blocks.append({"name": "stone", "x": x, "y": 0, "z": z})

# Build walls
for y in range(1, height):
    for x in range(width):
        for z in range(depth):
            if x in (0, width-1) or z in (0, depth-1):
                blocks.append({"name": "planks", "x": x, "y": y, "z": z})

# Add roof
for x in range(width):
    for z in range(depth):
        blocks.append({"name": "planks", "x": x, "y": height, "z": z})
```"""

        prompt = f"""Generate Python code to build a Minecraft structure with these specifications:
{json.dumps(plan, indent=2)}

- Generate code that creates a structure matching the specifications.
- Each block should have: name, x, y, z coordinates.
- Return a list of blocks to place relative to a starting position in a variable named 'blocks'.
- Use only valid Minecraft block types.
Return only the Python code in the answer block."""

        code_response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={"user_input": prompt, "context": context},
        )
        code_response = str(code_response).strip()
        if "```python" in code_response:
            code_response = code_response.split("```python")[1]
        if "```" in code_response:
            code_response = code_response.split("```")[0]
        code_response = code_response.strip()

        # Execute the generated code
        try:
            # Prepare a namespace for code execution
            namespace = {"blocks": []}

            # Define allowed built-ins
            safe_builtins = {
                "range": range,
                "min": min,
                "max": max,
                "int": int,
                "float": float,
                "str": str,
                "blocks": namespace["blocks"],
            }

            # Execute the code safely
            exec(code_response, {"__builtins__": safe_builtins}, namespace)

            blocks = namespace.get("blocks", [])
            block_objects = [Block(**b) for b in blocks]

            return Structure(
                name=f"{plan.get('type', 'custom')}_{plan.get('style', 'default')}",
                blocks=block_objects,
            )

        except Exception as e:
            print(f"Failed to generate structure: {e}")
            # Fallback to simple shelter
            return self.structure_templates.get("dirt_shelter")

    async def place_block_command(
        self, block_type: str, x: int, y: int, z: int, properties: Optional[Dict] = None
    ):
        """Wrapper command to be called externally"""
        await self.place_block(block_type, x, y, z, properties)
