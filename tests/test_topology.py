import sys
import unittest
import weakref
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))

from spektrafilm.runtime.topology import Node, run_topology


class TopologyTests(unittest.TestCase):
    def test_consumed_full_frame_taps_are_released_before_later_stages(self):
        source_ref = None

        def make_source():
            nonlocal source_ref
            source = np.ones((32, 48, 3), dtype=np.float64)
            source_ref = weakref.ref(source)
            return source

        def develop(source):
            return source.copy()

        def scan(negative):
            self.assertIsNone(source_ref())
            return negative * 0.5

        output = run_topology(
            [
                Node(('source',), ('negative',), develop, 'develop'),
                Node(('negative',), ('output',), scan, 'scan'),
            ],
            'source', 'output', make_source(),
        )
        np.testing.assert_array_equal(output, np.full((32, 48, 3), 0.5))


if __name__ == '__main__':
    unittest.main()
