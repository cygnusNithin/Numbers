
"""
Draw identification and prize-category lookup.

Returns:
- Draw metadata
- Prize categories
- Prize amounts
- Number count per prize category

Does not return winning numbers.
"""

import re
from pathlib import Path

from pymongo import MongoClient


VIDEO_SERIAL_PATTERN = re.compile(
    r"\b([A-Z]{2,5}-\d+)\b",
    re.IGNORECASE,
)


class DrawLookup:
    def __init__(
        self,
        mongo_uri="mongodb://localhost:27017",
        database="numbergrid",
        collection="absolute_data_v2",
    ):
        self.client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000,
        )

        self.db = self.client[database]
        self.collection = self.db[collection]

    @staticmethod
    def extract_serial(filename):
        """
        Extract draw serial from video filename.

        Example:
        Kerala Lottery Official Live - SAMRUDHI
        - SM-70 - 30.08.2026.mp4

        Returns:
        SM-70
        """

        name = Path(filename).stem

        matches = VIDEO_SERIAL_PATTERN.findall(name)

        if not matches:
            raise ValueError(
                f"Could not identify draw serial from filename: {filename}"
            )

        # Prefer the final serial candidate.
        serial = matches[-1].upper()

        return serial

    def find_draw(self, serial_number):
        """
        Find draw metadata and prize categories.

        Returns:
        - serialNumber
        - date
        - drawDate
        - drawCategory
        - fileName
        - prizeCategories:
            - prizeCategory
            - prize
            - numberCount

        Winning numbers are never returned.
        """

        pipeline = [
            {
                "$match": {
                    "serialNumber": serial_number.upper()
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "serialNumber": 1,
                    "date": 1,
                    "drawDate": 1,
                    "drawCategory": 1,
                    "fileName": 1,

                    "prizeCategories": {
                        "$map": {
                            "input": {
                                "$ifNull": ["$series", []]
                            },
                            "as": "item",
                            "in": {
                                "prizeCategory": "$$item.prizeCategory",
                                "prize": "$$item.prize",

                                "numberCount": {
                                    "$size": {
                                        "$ifNull": [
                                            "$$item.numbers",
                                            []
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            },
            {
                "$limit": 1
            }
        ]

        results = list(
            self.collection.aggregate(pipeline)
        )

        if not results:
            return None

        return results[0]

    def close(self):
        """Close MongoDB connection."""
        self.client.close()
