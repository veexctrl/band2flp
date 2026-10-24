import json
import unittest

import plistlib

from research.scripts.keyed_archive_inventory import profile_archive


class KeyedArchiveInventoryTests(unittest.TestCase):
    def test_counts_schema_keywords_without_emitting_dictionary_keys(self) -> None:
        objects = [
            "$null",
            {"$classname": "NSMutableDictionary"},
            {"NS.string": "arrangeTrackUUID"},
            {"NS.string": "automationMode"},
            {
                "$class": plistlib.UID(1),
                "NS.keys": [plistlib.UID(2), plistlib.UID(3)],
                "NS.objects": [plistlib.UID(0), plistlib.UID(0)],
            },
            {"$class": plistlib.UID(1), "TrackRecordVisible": True},
        ]

        result = profile_archive({"$objects": objects})

        self.assertEqual(
            result["dictionary_keyword_key_counts"],
            {"automation": 1, "track": 1},
        )
        self.assertEqual(
            result["dictionary_keyword_key_counts_by_class"],
            {"NSMutableDictionary": {"automation": 1, "track": 1}},
        )
        self.assertEqual(result["object_field_keyword_counts"], {"track": 1})
        self.assertEqual(
            result["object_field_keyword_counts_by_class"],
            {"NSMutableDictionary": {"track": 1}},
        )
        self.assertNotIn("arrangeTrackUUID", json.dumps(result))
        self.assertNotIn("automationMode", json.dumps(result))


if __name__ == "__main__":
    unittest.main()

