"""Integrationstests für scripts/build-release.sh (Release-Pakete für GitHub).

Die Tests arbeiten in einer temporären Kopie des Repositorys (git clone), in die der
aktuelle Stand von Build-Skript, CHANGELOG, Version und pyproject.toml übernommen und
committet wird. Version und CHANGELOG-Abschnitt werden dort kontrolliert gesetzt,
damit die Tests nicht vom echten Versionsstand abhängen.
"""

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build-release.sh"
TEST_VERSION = "9.8.7"
TEST_HEADING = "## 9.8 – Testmonat 2099"
CHANGELOG_WITH_SECTION = f"""# Änderungsprotokoll

{TEST_HEADING}

- Neu: Testeintrag für das Release.

## 9.7 – Vorgänger

- Alter Eintrag, darf nicht in den Release-Notizen stehen.
"""
CHANGELOG_WITHOUT_SECTION = """# Änderungsprotokoll

## 9.7 – Vorgänger

- Alter Eintrag.
"""
FILES_FROM_WORKTREE = (
    "scripts/build-release.sh",
    "CHANGELOG.md",
    "musik_bingo/__init__.py",
    "pyproject.toml",
)


def _git_environment():
    """Umgebung ohne GIT_*-Variablen, damit kein fremdes Repository angesprochen wird."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["LC_ALL"] = "C.UTF-8"
    return environment


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Release Test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        env=_git_environment(),
    )


def _git_available():
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True,
        env=_git_environment(),
    )
    return result.returncode == 0


def _make_repo(base, version=TEST_VERSION, changelog=CHANGELOG_WITH_SECTION, starter_executable=True):
    """Klont das Projekt nach base/repo und committet den kontrollierten Release-Stand."""
    repo = Path(base) / "repo"
    subprocess.run(
        ["git", "clone", "--quiet", str(PROJECT_ROOT), str(repo)],
        check=True,
        capture_output=True,
        env=_git_environment(),
    )
    for relative in FILES_FROM_WORKTREE:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative, target)

    init_file = repo / "musik_bingo" / "__init__.py"
    init_text = init_file.read_text(encoding="utf-8")
    init_file.write_text(
        re.sub(r'^__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"', init_text, flags=re.M),
        encoding="utf-8",
    )
    pyproject = repo / "pyproject.toml"
    pyproject.write_text(
        re.sub(r'^version\s*=\s*"[^"]*"', f'version = "{version}"', pyproject.read_text(encoding="utf-8"),
               count=1, flags=re.M),
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    _git(repo, "add", *FILES_FROM_WORKTREE)
    _git(repo, "update-index", "--chmod=+x", "scripts/build-release.sh")
    if not starter_executable:
        _git(repo, "update-index", "--chmod=-x", "scripts/starten.sh")
        (repo / "scripts" / "starten.sh").chmod(0o644)
    _git(repo, "commit", "--quiet", "--allow-empty", "-m", "Testrelease")

    # Nicht verfolgte Datei (z. B. Spielstand) darf nicht im Paket landen.
    (repo / "spielstand_privat.json").write_text("{}", encoding="utf-8")
    return repo


def _commit_all(repo, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-q", "-am", message], check=True, capture_output=True)


def _build(repo, *args):
    return subprocess.run(
        ["bash", str(repo / "scripts" / "build-release.sh"), *args],
        capture_output=True,
        text=True,
        env=_git_environment(),
        cwd=tempfile.gettempdir(),
    )


@unittest.skipUnless(_git_available(), "git oder Git-Repository nicht verfügbar")
class ReleaseBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = _make_repo(cls._tmp.name)
        cls.dist = Path(cls._tmp.name) / "ausgabe"
        cls.result = _build(cls.repo, f"v{TEST_VERSION}", str(cls.dist))
        cls.name = f"musik-bingo-{TEST_VERSION}"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_build_succeeds_and_creates_all_files(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        for file_name in (f"{self.name}.zip", f"{self.name}.tar.gz", "SHA256SUMS", "RELEASE_NOTES.md"):
            self.assertTrue((self.dist / file_name).is_file(), file_name)

    def test_zip_has_top_folder_and_required_files(self):
        with zipfile.ZipFile(self.dist / f"{self.name}.zip") as archive:
            names = archive.namelist()
        self.assertTrue(names)
        self.assertTrue(all(name.startswith(f"{self.name}/") for name in names), names[:5])
        for required in ("scripts/install-desktop.sh", "musik_bingo/data/default_songs.txt", "README.md",
                         "scripts/build-release.sh"):
            self.assertIn(f"{self.name}/{required}", names)
        self.assertFalse(any("/.git/" in name or name.endswith("/.git") for name in names))
        self.assertNotIn(f"{self.name}/spielstand_privat.json", names)

    def test_zip_contains_committed_version(self):
        with zipfile.ZipFile(self.dist / f"{self.name}.zip") as archive:
            init_text = archive.read(f"{self.name}/musik_bingo/__init__.py").decode("utf-8")
        self.assertIn(f'__version__ = "{TEST_VERSION}"', init_text)

    def test_sha256sums_verify(self):
        lines = (self.dist / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            digest, file_name = line.split(maxsplit=1)
            data = (self.dist / file_name.lstrip("*")).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, file_name)
        if shutil.which("sha256sum"):
            subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=self.dist, check=True)

    def test_release_notes_contain_section_and_install_hint(self):
        notes = (self.dist / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        self.assertTrue(notes.startswith(TEST_HEADING), notes[:80])
        self.assertIn("Testeintrag für das Release", notes)
        self.assertNotIn("Vorgänger", notes)
        self.assertIn("bash scripts/install-desktop.sh", notes)
        self.assertIn(f"{self.name}.zip", notes)

    def test_tar_gz_keeps_executable_bit(self):
        with tarfile.open(self.dist / f"{self.name}.tar.gz") as archive:
            members = {member.name: member for member in archive.getmembers()}
        self.assertIn(f"{self.name}/README.md", members)
        self.assertFalse(any("/.git/" in name for name in members))
        starter = members[f"{self.name}/scripts/starten.sh"]
        self.assertTrue(starter.mode & stat.S_IXUSR, oct(starter.mode))


@unittest.skipUnless(_git_available(), "git oder Git-Repository nicht verfügbar")
class ReleaseBuildFailureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dist = Path(self._tmp.name) / "ausgabe"

    def test_wrong_tag_fails_with_german_message(self):
        repo = _make_repo(self._tmp.name)
        result = _build(repo, "v1.0.0", str(self.dist))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("passt nicht zur Version", result.stderr)
        self.assertIn(f"v{TEST_VERSION}", result.stderr)
        self.assertFalse(list(self.dist.glob("*.zip")))

    def test_missing_changelog_section_fails(self):
        repo = _make_repo(self._tmp.name, changelog=CHANGELOG_WITHOUT_SECTION)
        result = _build(repo, f"v{TEST_VERSION}", str(self.dist))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHANGELOG.md", result.stderr)
        self.assertIn("## 9.8", result.stderr)
        self.assertFalse(list(self.dist.glob("*.zip")))

    def test_pyproject_version_mismatch_fails(self):
        repo = _make_repo(self._tmp.name)
        pyproject = repo / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(f'version = "{TEST_VERSION}"', 'version = "0.0.1"', 1),
            encoding="utf-8",
        )
        _commit_all(repo, "pyproject abweichend")
        result = _build(repo, "", str(self.dist))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pyproject.toml", result.stderr)

    def test_uncommitted_version_bump_is_not_packaged_under_new_number(self):
        """Regression: Version kam aus dem Arbeitsordner, Inhalt aus HEAD → ZIP mit falschem Inhalt."""
        repo = _make_repo(self._tmp.name)
        init = repo / "musik_bingo" / "__init__.py"
        init.write_text('__version__ = "9.9.9"\n', encoding="utf-8")  # nicht committet
        result = _build(repo, "v9.9.9", str(self.dist))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(self.dist.glob("*9.9.9*")))
        result = _build(repo, f"v{TEST_VERSION}", str(self.dist))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.dist / f"musik-bingo-{TEST_VERSION}.zip").is_file())

    def test_scripts_without_exec_bit_are_made_executable_in_tar_gz(self):
        repo = _make_repo(self._tmp.name, starter_executable=False)
        result = _build(repo, f"v{TEST_VERSION}", str(self.dist))
        self.assertEqual(result.returncode, 0, result.stderr)
        name = f"musik-bingo-{TEST_VERSION}"
        with tarfile.open(self.dist / f"{name}.tar.gz") as archive:
            starter = archive.getmember(f"{name}/scripts/starten.sh")
            names = archive.getnames()
        self.assertTrue(starter.mode & stat.S_IXUSR, oct(starter.mode))
        self.assertTrue(all(entry == name or entry.startswith(f"{name}/") for entry in names))
        subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=self.dist, check=True)


if __name__ == "__main__":
    unittest.main()
