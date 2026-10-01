import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import verify_evidence as v

class ReleaseVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'repo';self.root.mkdir()
        (self.root/'a.txt').write_text('scientific bytes\n')
        self.man=self.root/'PUBLIC_RELEASE_SHA256SUMS.txt'
        self.man.write_text(v.sha256(self.root/'a.txt')+'  ./a.txt\n')
    def tearDown(self):self.tmp.cleanup()
    def invoke(self,*args):
        return subprocess.run([sys.executable,str(Path(v.__file__)), '--root',str(self.root),*args],text=True,capture_output=True)
    def test_public_manifest_autodetection(self):self.assertEqual(self.invoke().returncode,0)
    def test_dot_slash_is_normalized(self):self.assertEqual(v.parse_manifest(self.root,self.man),{'a.txt':v.sha256(self.root/'a.txt')})
    def test_modified_bytes_are_rejected(self):
        (self.root/'a.txt').write_text('changed');self.assertNotEqual(self.invoke().returncode,0)
    def test_missing_file_rejected(self):
        (self.root/'a.txt').unlink();self.assertNotEqual(self.invoke().returncode,0)
    def test_unlisted_file_rejected(self):
        (self.root/'extra').write_text('x');self.assertNotEqual(self.invoke().returncode,0)
    def test_duplicate_alias_rejected(self):
        self.man.write_text(self.man.read_text()+v.sha256(self.root/'a.txt')+'  a.txt\n')
        self.assertNotEqual(self.invoke().returncode,0)
    def test_traversal_rejected(self):
        self.man.write_text('0'*64+'  ../a.txt\n');self.assertNotEqual(self.invoke().returncode,0)
    def test_absolute_path_rejected(self):
        self.man.write_text('0'*64+'  /tmp/a.txt\n');self.assertNotEqual(self.invoke().returncode,0)
    def test_malformed_hash_rejected(self):
        self.man.write_text('wrong  a.txt\n');self.assertNotEqual(self.invoke().returncode,0)
    def test_empty_manifest_rejected(self):
        self.man.write_text('');self.assertNotEqual(self.invoke().returncode,0)
    def test_ambiguous_manifest_rejected(self):
        (self.root/'EVIDENCE_SHA256SUMS.txt').write_text(self.man.read_text());self.assertNotEqual(self.invoke().returncode,0)
    def test_symlink_escape_rejected(self):
        (self.root/'a.txt').unlink();outside=Path(self.tmp.name)/'outside.txt';outside.write_text('scientific bytes\n')
        (self.root/'a.txt').symlink_to(outside);self.assertNotEqual(self.invoke().returncode,0)
    def test_failure_does_not_rewrite_manifest(self):
        before=self.man.read_bytes();(self.root/'a.txt').write_text('tamper')
        self.invoke();self.assertEqual(before,self.man.read_bytes())
    def test_self_hash_rejected(self):
        self.man.write_text('0'*64+'  PUBLIC_RELEASE_SHA256SUMS.txt\n');self.assertNotEqual(self.invoke().returncode,0)
    def test_explicit_builder_guard_and_dry_run(self):
        previous=Path(self.tmp.name)/'previous.txt';previous.write_bytes(self.man.read_bytes())
        plan=Path(self.tmp.name)/'changes.json';plan.write_text(json.dumps({'approved_changes':[],'approved_additions':[]}))
        cmd=[sys.executable,str(Path(v.__file__).with_name('build_public_manifest.py')),'--root',str(self.root),
             '--previous-manifest',str(previous),'--change-plan',str(plan)]
        before=self.man.read_bytes();(self.root/'a.txt').write_text('deliberate release update')
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        self.assertEqual(before,self.man.read_bytes())
        plan.write_text(json.dumps({'approved_changes':['a.txt'],'approved_additions':[]}))
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        self.assertEqual(before,self.man.read_bytes())
        self.assertEqual(subprocess.run(cmd+['--write'],capture_output=True).returncode,0)
        self.assertEqual(self.invoke().returncode,0)

if __name__=='__main__':unittest.main(verbosity=2)
