"""Check attachment integrity, safe paths and preservation of local evidence."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import stat

SCRIPT = Path(__file__).resolve().parents[1]/'phase1-reproduction/verify_copy.py'
spec = importlib.util.spec_from_file_location('phase1_verify', SCRIPT)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = 'records/run/log.txt'
        data = b'frozen log\n'
        self.manifest = {'files': [{'path': self.path, 'type': 'file', 'bytes': len(data),
                                    'sha256': hashlib.sha256(data).hexdigest()}]}

    def bundle(self, entries):
        archive = self.root/'attachment.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for name, data in entries:
                z.writestr(name, data)
        return archive, {'bytes': archive.stat().st_size, 'sha256': verify.file_hash(archive)}

    def test_restore_and_identical_second_restore(self):
        z, asset = self.bundle([(self.path, b'frozen log\n')])
        for _ in range(2):
            self.assertEqual(verify.restore_records(self.root, self.manifest, z, asset), 1)
        self.assertEqual((self.root/self.path).read_bytes(), b'frozen log\n')

    def test_tampered_download_rejected(self):
        z, asset = self.bundle([(self.path, b'frozen log\n')])
        z.write_bytes(z.read_bytes()+b'changed')
        with self.assertRaises(ValueError):
            verify.restore_records(self.root, self.manifest, z, asset)

    def test_unexpected_path_and_wrong_payload_rejected(self):
        for entries in [[('../outside', b'data')], [(self.path, b'wrong log\n')]]:
            z, asset = self.bundle(entries)
            with self.assertRaises(ValueError):
                verify.restore_records(self.root, self.manifest, z, asset)
        self.assertFalse((self.root/self.path).exists())

    def test_conflicting_local_log_preserved(self):
        file = self.root/self.path
        file.parent.mkdir(parents=True)
        file.write_bytes(b'local evidence')
        z, asset = self.bundle([(self.path, b'frozen log\n')])
        with self.assertRaises(ValueError):
            verify.restore_records(self.root, self.manifest, z, asset)
        self.assertEqual(file.read_bytes(), b'local evidence')

    def test_symlink_escape_rejected_before_restore(self):
        link = 'records/run/input'
        target = '../../../outside'
        self.manifest = {'files': [{'path': link, 'type': 'symlink', 'copied_link_target': target}]}
        archive = self.root/'attachment.zip'
        info = zipfile.ZipInfo(link)
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr(info, target)
        asset = {'bytes': archive.stat().st_size, 'sha256': verify.file_hash(archive)}
        with self.assertRaises(ValueError):
            verify.restore_records(self.root, self.manifest, archive, asset)
        self.assertFalse((self.root/'records').exists())


if __name__ == '__main__':
    unittest.main()
