from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'))
from write_ensemble_dummies import member_prefixes


class MemberTests(unittest.TestCase):
    def test_only_downloaded_flow_collections(self):
        paths = ['//DETO3/FLOW-UNREG/01JAN2026/1DAY/C:001981|/',
                 '//SLMO3/FLOW-LOC/01JAN2026/1DAY/C:001981|/',
                 '//SLMO3/FLOW-LOC/01JAN2027/1DAY/C:002027|/',
                 '/ZERO/ZERO/FLOW/01JAN2026/1DAY/C:001928|DUMMY/',
                 '//DET/ELEV/01JAN2026/1DAY/C:001929|/',
                 '//SLMO3/FLOW-LOC/01JAN2026/1DAY/A0/']
        self.assertEqual(member_prefixes(paths), ['C:001981|', 'C:002027|'])
