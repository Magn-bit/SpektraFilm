"""Regression for a RAW DLL loaded from a foreign Qt worker thread."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class RawThreadLifecycle(unittest.TestCase):
    def test_qt_raw_probe_and_decode_thread_can_exit(self):
        fixture = Path(os.environ.get('SPEKTRAFILM_RAW_FIXTURE', 'D:/Download/DSC09118.ARW'))
        if sys.platform != 'win32' or not fixture.is_file():
            self.skipTest('requires a local Windows RAW fixture')
        program = textwrap.dedent('''
            import gc, sys
            from PySide6.QtCore import QThreadPool, QRunnable
            from desktop.raw_development import probe_raw, decode_raw
            class Job(QRunnable):
                def run(self):
                    assert probe_raw(sys.argv[1])['source_width'] > 0
                    pixels, metadata = decode_raw(sys.argv[1], preview=True)
                    assert pixels.shape[2] == 3 and not pixels.flags.writeable
                    del pixels, metadata
                    gc.collect()
            pool = QThreadPool()
            pool.start(Job())
            pool.waitForDone()
            print('RAW Qt worker exited safely', flush=True)
        ''')
        process = subprocess.run([sys.executable, '-c', program, str(fixture)],
                                 capture_output=True, text=True, timeout=45,
                                 env=dict(os.environ, PYTHONFAULTHANDLER='1'))
        self.assertEqual(process.returncode, 0, process.stdout+process.stderr)
        self.assertIn('RAW Qt worker exited safely', process.stdout)


if __name__ == '__main__':
    unittest.main()
