"""Recover interrupted file output without losing edits or overwriting results."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from desktop.batch_jobs import BatchExportJournal, source_matches
from desktop.controller import Controller, PhotoProvider
from desktop.imaging import Settings
from desktop.output import export_recipe
from shared.output_recipes import OutputRecipe


class BatchRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_interrupted_journal_preserves_snapshot_and_ignores_torn_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.arw'
            source.write_bytes(b'original camera data')
            settings = Settings(exposure=.75)
            journal = BatchExportJournal(root / 'journal')
            document = journal.create(OutputRecipe(), [(source, root / 'result.jpg', settings)])
            journal.record(document['job_id'], 0, 'failed', error='disk unavailable')
            events = journal._events_path(document['job_id'])
            with events.open('ab') as stream:
                stream.write(b'{"job_id":')
            recovered = BatchExportJournal(root / 'journal').load()
            item = recovered['items'][0]
            self.assertEqual(item['status'], 'failed')
            self.assertEqual(item['error'], 'disk unavailable')
            self.assertEqual(item['settings']['exposure'], .75)
            self.assertTrue(source_matches(str(source), item['source_identity']))
            source.write_bytes(b'changed camera data with different size')
            self.assertFalse(source_matches(str(source), item['source_identity']))
            document['job_id'] = '../' + 'a' * 29
            journal.manifest_path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaises(ValueError):
                BatchExportJournal(root / 'journal').load()

            # Reject a plan that a later restart could not read, preserving
            # the previously active record and removing the unused event log.
            before = set(journal.directory.iterdir())
            with patch('desktop.batch_jobs.MAX_MANIFEST_BYTES', 64):
                with self.assertRaises(ValueError):
                    journal.create(OutputRecipe(), [(source, root / 'other.jpg', settings)])
            self.assertEqual(set(journal.directory.iterdir()), before)

    def test_actual_output_failure_restart_retry_and_collision_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plans = []
            for index in range(3):
                source, target = root / f'source{index}.arw', root / f'out{index}.arw'
                source.write_bytes(bytes([index + 1]) * (128 + index))
                plans.append((str(source), str(target), Settings(exposure=index / 10)))
            recipe = OutputRecipe(id='recovery-raw', format='raw', bit_depth=16)
            ctrl = Controller(PhotoProvider(), directory)
            jobs, progress = [], []
            ctrl.stateChanged.connect(lambda: progress.append(ctrl.batchProgress))
            try:
                def fail_second(source, target, *args, **kwargs):
                    if source == plans[1][0]:
                        raise OSError('test disk interruption')
                    return export_recipe(source, target, *args, **kwargs)
                with patch.object(ctrl.export_pool, 'start', side_effect=jobs.append), \
                        patch.object(ctrl, '_begin_full_export'), \
                        patch('desktop.controller.export_recipe', side_effect=fail_second):
                    self.assertTrue(ctrl._start_recipe_export(plans, recipe))
                    jobs.pop().run()
                self.assertEqual([item['status'] for item in ctrl.exportItems], ['completed', 'failed', 'completed'])
                self.assertEqual(ctrl.batchProgress, 3)
                self.assertEqual(progress, sorted(progress))
                self.assertLessEqual(max(progress), 3)
                self.assertTrue(ctrl._batch_journal.manifest_path.exists())
            finally:
                ctrl.close()

            # A result created by another application between attempts must
            # survive retry; recovery chooses a new output filename.
            Path(plans[1][1]).write_bytes(b'external result')
            ctrl = Controller(PhotoProvider(), directory)
            jobs = []
            try:
                self.assertTrue(ctrl.pendingBatchRecovery)
                self.assertFalse(ctrl.canResumeBatchExport)
                self.assertTrue(ctrl.canRetryFailedExports)
                self.assertEqual(ctrl._batch_plan[1]['settings'].exposure, .1)
                with patch.object(ctrl.export_pool, 'start', side_effect=jobs.append), \
                        patch.object(ctrl, '_begin_full_export'):
                    ctrl.retryFailedExports()
                    jobs.pop().run()
                self.assertEqual([item['status'] for item in ctrl.exportItems], ['completed'] * 3)
                retry = Path(ctrl.exportItems[1]['output'])
                self.assertEqual(retry.name, 'out1_2.arw')
                self.assertEqual(retry.read_bytes(), Path(plans[1][0]).read_bytes())
                self.assertEqual(Path(plans[1][1]).read_bytes(), b'external result')
                self.assertFalse(ctrl._batch_journal.manifest_path.exists())
            finally:
                ctrl.close()
            ctrl = Controller(PhotoProvider(), directory)
            try:
                self.assertFalse(ctrl.pendingBatchRecovery)
                self.assertEqual(ctrl.exportItems, [])
            finally:
                ctrl.close()

    def test_switching_photos_keeps_masks_selection_and_history_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ctrl = Controller(PhotoProvider(), directory)
            try:
                ctrl._photo_model.append([
                    dict(path=str(root / f'image{index}.png'), name=f'image{index}.png',
                         width=320, height=240, dimensions='320 × 240', thumbnail='',
                         settings=asdict(Settings()))
                    for index in range(2)])
                ctrl.selectPhoto(0)
                brush = ctrl.addMaskOfKind('brush')
                ctrl.addMaskOfKind('linear')
                ctrl.selectMask(brush)
                token = ctrl.beginMaskStroke(.2, .3, .05, .7, 1., False)
                ctrl.appendMaskPoints(token, [[.3, .4]])
                ctrl.selectPhoto(1)
                self.assertEqual(ctrl.maskLayers, [])
                self.assertEqual(ctrl.activeMaskId, '')
                # A queued pointer batch from the previous photograph cannot
                # create or edit a mask in the newly active photograph.
                ctrl.appendMaskPoints(token, [[.7, .8]])
                ctrl.endMaskStroke(token)
                self.assertEqual(ctrl.maskLayers, [])
                radial = ctrl.addMaskOfKind('radial')
                ctrl.updateMaskParameter('exposure', .6)
                ctrl.selectPhoto(0)
                self.assertEqual(ctrl.activeMaskId, brush)
                self.assertEqual(len(ctrl.activeMask['strokes']), 1)
                self.assertEqual(len(ctrl.activeMask['strokes'][0]['points']), 2)
                ctrl.undo()
                self.assertEqual(ctrl.activeMask['strokes'], [])
                ctrl.selectPhoto(1)
                self.assertEqual(ctrl.activeMaskId, radial)
                self.assertEqual(ctrl.activeMask['exposure'], .6)
                self.assertEqual(len(ctrl.maskLayers), 1)
                ctrl.undo()
                self.assertEqual(ctrl.activeMask['exposure'], 0.)
                first = json.loads(ctrl._edit_path(str(root / 'image0.png')).read_text(encoding='utf-8'))
                self.assertEqual(len(first['settings']['masks']), 2)
                self.assertEqual(first['settings']['masks'][0]['strokes'], [])
            finally:
                ctrl.close()


if __name__ == '__main__':
    unittest.main()
