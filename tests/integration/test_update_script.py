"""Update per Klick (scripts/aktualisieren.sh) gegen ein lokales Git-„GitHub“ – ohne Netzwerk."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class UpdateScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {**os.environ, **GIT_ENV, "MUSIK_BINGO_OHNE_DIALOG": "1",
                    "XDG_DATA_HOME": str(self.tmp / "daten"), "XDG_RUNTIME_DIR": str(self.tmp)}
        self.origin = self.tmp / "github.git"
        self.source = self.tmp / "entwicklung"
        self.git("init", "--quiet", "--bare", "--initial-branch=main", str(self.origin))
        for part in ("scripts/aktualisieren.sh", "scripts/install-desktop.sh", "scripts/starten.sh",
                     "musik_bingo/data/icons"):
            target = self.source / part
            target.parent.mkdir(parents=True, exist_ok=True)
            if (PROJECT_ROOT / part).is_dir():
                shutil.copytree(PROJECT_ROOT / part, target)
            else:
                shutil.copy2(PROJECT_ROOT / part, target)
        self.set_version("1.0.0")
        self.git("init", "--quiet", "--initial-branch=main", cwd=self.source)
        self.git("remote", "add", "origin", str(self.origin), cwd=self.source)
        self.commit_and_push("Version 1.0.0")
        self.install = self.tmp / "installiert"
        self.git("clone", "--quiet", str(self.origin), str(self.install))

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True,
                              capture_output=True, text=True)

    def set_version(self, version):
        init = self.source / "musik_bingo" / "__init__.py"
        init.write_text(f'__version__ = "{version}"\n')

    def commit_and_push(self, message):
        self.git("add", "-A", cwd=self.source)
        self.git("commit", "--quiet", "-m", message, cwd=self.source)
        self.git("push", "--quiet", "origin", "main", cwd=self.source)

    def run_update(self, folder=None):
        folder = folder or self.install
        return subprocess.run(["bash", str(folder / "scripts" / "aktualisieren.sh")], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def installed_version(self):
        return (self.install / "musik_bingo" / "__init__.py").read_text()

    def test_updates_to_new_version_and_installs_both_menu_entries(self):
        self.set_version("1.1.0")
        self.commit_and_push("Version 1.1.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Version 1.0.0 → 1.1.0", result.stdout)
        self.assertIn("1.1.0", self.installed_version())
        apps = self.tmp / "daten" / "applications"
        self.assertTrue((apps / "musik-bingo.desktop").is_file())
        update_entry = (apps / "musik-bingo-aktualisieren.desktop").read_text()
        self.assertIn(f'Exec=/bin/bash "{self.install}/scripts/aktualisieren.sh"', update_entry)
        self.assertIn("Name=Musik Bingo aktualisieren", update_entry)
        self.assertIn("Terminal=false", update_entry)

        again = self.run_update()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("ist aktuell (Version 1.1.0)", again.stdout)

    def test_local_changes_are_never_overwritten(self):
        (self.install / "scripts" / "starten.sh").write_text("# eigene Änderung\n")
        self.set_version("1.2.0")
        self.commit_and_push("Version 1.2.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 1)
        self.assertIn("geänderte Dateien", result.stderr)
        self.assertEqual((self.install / "scripts" / "starten.sh").read_text(), "# eigene Änderung\n")
        self.assertIn("1.0.0", self.installed_version())

    def test_unreachable_github_changes_nothing(self):
        self.git("remote", "set-url", "origin", str(self.tmp / "gibt-es-nicht.git"), cwd=self.install)
        result = self.run_update()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Update fehlgeschlagen", result.stderr)
        self.assertIn("1.0.0", self.installed_version())
        self.assertFalse((self.tmp / "daten" / "applications").exists())

    def test_zip_installation_points_to_release_page(self):
        zip_copy = self.tmp / "zip"
        shutil.copytree(self.install, zip_copy, ignore=shutil.ignore_patterns(".git"))
        result = self.run_update(zip_copy)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Keine Git-Kopie", result.stderr)
        self.assertIn("/releases", result.stderr)

    def test_switches_back_to_main_branch(self):
        self.git("checkout", "--quiet", "-b", "alter-zweig", cwd=self.install)
        self.set_version("1.3.0")
        self.commit_and_push("Version 1.3.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.install).stdout.strip()
        self.assertEqual(branch, "main")
        self.assertIn("1.3.0", self.installed_version())
        # Ein späteres „git pull“ im Terminal muss weiter funktionieren (Tracking gesetzt)
        upstream = self.git("rev-parse", "--abbrev-ref", "main@{upstream}", cwd=self.install).stdout.strip()
        self.assertEqual(upstream, "origin/main")

    def test_refuses_while_app_is_running(self):
        app = subprocess.Popen(["python3", "-c", "import time; time.sleep(30)", "-m", "musik_bingo.main"])
        self.addCleanup(app.wait)  # erst beenden UND abwarten, sonst sieht der nächste Test ihn noch
        self.addCleanup(app.kill)
        self.set_version("1.4.0")
        self.commit_and_push("Version 1.4.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 1)
        self.assertIn("läuft noch", result.stderr)
        self.assertIn("1.0.0", self.installed_version())

    def branch(self):
        return self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.install).stdout.strip()

    def head(self):
        return self.git("rev-parse", "HEAD", cwd=self.install).stdout.strip()

    def test_unmerged_feature_branch_is_never_downgraded(self):
        """Regression (Fable): Ein noch nicht gemergter Entwicklungsstand wurde auf main zurückgesetzt."""
        self.git("checkout", "--quiet", "-b", "feature/neu", cwd=self.install)
        (self.install / "neu.txt").write_text("neue Funktion\n")
        self.git("add", "neu.txt", cwd=self.install)
        self.git("commit", "--quiet", "-m", "neu", cwd=self.install)
        before = self.head()
        self.set_version("1.1.0")
        self.commit_and_push("Version 1.1.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 1)
        self.assertIn("noch nicht in 'main' übernommen", result.stderr)
        self.assertIn("nichts verändert", result.stderr)
        self.assertEqual((self.branch(), self.head()), ("feature/neu", before))
        self.assertTrue((self.install / "neu.txt").is_file())

    def test_diverged_local_main_changes_nothing(self):
        """Regression (Fable): Bei abweichendem lokalem main wurde schon der Zweig gewechselt."""
        self.git("commit", "--quiet", "--allow-empty", "-m", "lokal", cwd=self.install)  # main weicht ab
        self.git("checkout", "--quiet", "-b", "alt", "HEAD~1", cwd=self.install)
        before = self.head()
        self.set_version("1.1.0")
        self.commit_and_push("Version 1.1.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 1)
        self.assertIn("weicht von GitHub ab", result.stderr)
        self.assertEqual((self.branch(), self.head()), ("alt", before))

    def test_local_commits_on_main_are_kept(self):
        self.git("commit", "--quiet", "--allow-empty", "-m", "lokal", cwd=self.install)
        before = self.head()
        self.set_version("1.1.0")
        self.commit_and_push("Version 1.1.0")
        result = self.run_update()
        self.assertEqual(result.returncode, 1)
        self.assertIn("eigene Änderungen", result.stderr)
        self.assertEqual(self.head(), before)

    def test_new_state_with_same_version_is_reported_as_update(self):
        """Regression (Fable): gleiche Versionsnummer, neuer Stand → fälschlich „ist aktuell“."""
        (self.source / "fix.txt").write_text("Fehlerbehebung\n")
        self.commit_and_push("Fix ohne Versionssprung")
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Version 1.0.0 → 1.0.0 (neuer Stand)", result.stdout)
        self.assertTrue((self.install / "fix.txt").is_file())

    def test_single_branch_clone_of_merged_feature_branch_updates(self):
        """Regression (Fable, 2. Durchgang): Klon nur eines Zweigs → origin/main fehlte, Update hing fest."""
        self.git("checkout", "--quiet", "-b", "feature/x", cwd=self.source)
        (self.source / "x.txt").write_text("x\n")
        self.git("add", "x.txt", cwd=self.source)
        self.git("commit", "--quiet", "-m", "x", cwd=self.source)
        self.git("push", "--quiet", "origin", "feature/x", cwd=self.source)
        single = self.tmp / "einzweig"
        self.git("clone", "--quiet", "--single-branch", "-b", "feature/x", str(self.origin), str(single))
        self.git("checkout", "--quiet", "main", cwd=self.source)
        self.git("merge", "--quiet", "--no-ff", "-m", "merge", "feature/x", cwd=self.source)
        self.set_version("1.1.0")
        self.commit_and_push("Version 1.1.0")
        result = self.run_update(single)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Version 1.0.0 → 1.1.0", result.stdout)
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=single).stdout.strip()
        self.assertEqual(branch, "main")
        self.assertTrue((single / "x.txt").is_file())

    def test_script_syntax(self):
        subprocess.run(["bash", "-n", str(PROJECT_ROOT / "scripts" / "aktualisieren.sh")], check=True)


if __name__ == "__main__":
    unittest.main()
