import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publisher', ROOT / 'scripts/publish_public_study.py')
publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)

def run(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

class PublicationTests(unittest.TestCase):
    def test_repeated_run_and_racing_editor_keep_both_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); remote = base/'remote.git'; repo = base/'worker'; editor = base/'editor'
            subprocess.run(['git','init','-q','--bare',str(remote)],check=True)
            subprocess.run(['git','clone','-q',str(remote),str(repo)],check=True)
            run(repo,'checkout','-b','main')
            for r in [repo]:
                run(r,'config','user.name','Test');run(r,'config','user.email','test@example.invalid')
            (repo/'scripts').mkdir()
            shutil.copy(ROOT/'scripts/build_public_reports.py',repo/'scripts')
            run(repo,'add','.');run(repo,'commit','-m','baseline');run(repo,'push','-u','origin','main')
            subprocess.run(['git','clone','-q','--branch','main',str(remote),str(editor)],check=True)
            run(editor,'config','user.name','Editor');run(editor,'config','user.email','editor@example.invalid')
            def race(attempt):
                if attempt==0:
                    (editor/'editor-note.txt').write_text('preserve editor change')
                    run(editor,'add','.');run(editor,'commit','-m','concurrent edit');run(editor,'push','origin','main')
            original = run(repo,'rev-parse','HEAD')
            first=publisher.publish(repo,before_push=race,build_args=('--date','2099-01-02'))
            second=publisher.publish(repo,build_args=('--date','2099-01-02'))
            self.assertEqual(first,second)
            self.assertEqual(run(repo,'rev-parse','HEAD'),original)  # no destructive reset of user's checkout
            run(editor,'pull','--ff-only','origin','main')
            self.assertEqual((editor/'editor-note.txt').read_text(),'preserve editor change')
            self.assertEqual(len(list((editor/'reports/daily').glob('*.html'))),1)
            self.assertEqual(run(editor,'rev-list','--count','main'),'3')

if __name__=='__main__':unittest.main()
