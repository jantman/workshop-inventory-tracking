"""Unit tests for version resolution.

Every row of the resolution table in
`specs/047-build-version-suffix/data-model.md` is covered here.

The git-backed cases monkeypatch `app.version._git` rather than building fixture
repositories. That is not only faster -- it is the only way to represent the two
failure modes that matter most: `git` not installed, and `git` hanging. A real
repository cannot be made to exhibit either. The one test that must exercise the
real subprocess boundary, `TestGitHelper`, does so deliberately and does not use
the stub.
"""

import subprocess
import tomllib
from pathlib import Path

import pytest

from app import version as version_module
from app.version import RELEASE_VERSION, _compute_version, _git


# The stub answers are keyed on the first argument of the git invocation, which
# is enough to tell the three questions apart.
def _stub_git(monkeypatch, *, commit=None, tags=None, dirty=None):
    """Replace app.version._git with canned answers.

    `commit`, `tags` and `dirty` are the raw stdout each git call would produce,
    or None for "git could not answer". `tags` accepts a list for readability.
    """
    if isinstance(tags, list):
        tags = "\n".join(tags)

    answers = {"rev-parse": commit, "tag": tags, "status": dirty}
    calls = []

    def fake_git(*args: str):
        calls.append(args)
        return answers[args[0]]

    monkeypatch.setattr(version_module, "_git", fake_git)
    return calls


class TestReleaseVersion:
    """RELEASE_VERSION is pyproject.toml's version and nothing else."""

    @pytest.mark.unit
    def test_matches_pyproject(self):
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as f:
            declared = tomllib.load(f)["project"]["version"]
        assert RELEASE_VERSION == declared


class TestBuildStamp:
    """APP_BUILD_SHA is how a container learns what it was built from."""

    @pytest.mark.unit
    def test_full_sha_is_truncated_to_seven(self, monkeypatch):
        monkeypatch.setenv("APP_BUILD_SHA", "6d15bde4d4cda7c8ec7a0e277cf926ad2bf7881c")
        assert _compute_version("0.1.1") == "0.1.1-6d15bde"

    @pytest.mark.unit
    def test_already_short_sha_is_used_as_is(self, monkeypatch):
        monkeypatch.setenv("APP_BUILD_SHA", "6d15bde")
        assert _compute_version("0.1.1") == "0.1.1-6d15bde"

    @pytest.mark.unit
    def test_stamp_wins_over_the_working_copy(self, monkeypatch):
        """A container started inside a working copy reports what it was built from."""
        calls = _stub_git(monkeypatch, commit="abc1234", tags=[], dirty=" M app/x.py")
        monkeypatch.setenv("APP_BUILD_SHA", "6d15bde4d4cda7c8ec7a0e277cf926ad2bf7881c")

        assert _compute_version("0.1.1") == "0.1.1-6d15bde"
        assert calls == [], "git must not be consulted when a build stamp is present"

    @pytest.mark.unit
    @pytest.mark.parametrize("stamp", ["", "   ", "\n"])
    def test_empty_stamp_is_treated_as_absent(self, monkeypatch, stamp):
        """An unpassed build arg leaves ENV set but empty; that is not a stamp."""
        _stub_git(monkeypatch, commit="abc1234", tags=[], dirty="")
        monkeypatch.setenv("APP_BUILD_SHA", stamp)
        assert _compute_version("0.1.1") == "0.1.1-abc1234"

    @pytest.mark.unit
    def test_unset_stamp_falls_through_to_git(self, monkeypatch):
        _stub_git(monkeypatch, commit="abc1234", tags=[], dirty="")
        monkeypatch.delenv("APP_BUILD_SHA", raising=False)
        assert _compute_version("0.1.1") == "0.1.1-abc1234"


class TestWorkingCopy:
    """With no stamp, the working copy is asked directly."""

    @pytest.fixture(autouse=True)
    def _no_stamp(self, monkeypatch):
        monkeypatch.delenv("APP_BUILD_SHA", raising=False)

    @pytest.mark.unit
    def test_on_release_tag_and_clean(self, monkeypatch):
        _stub_git(monkeypatch, commit="6d15bde", tags=["v0.1.1"], dirty="")
        assert _compute_version("0.1.1") == "0.1.1"

    @pytest.mark.unit
    def test_on_release_tag_and_dirty(self, monkeypatch):
        """Edited code is not the tagged code, tag or no tag."""
        _stub_git(monkeypatch, commit="6d15bde", tags=["v0.1.1"], dirty=" M app/x.py")
        assert _compute_version("0.1.1") == "0.1.1-dirty"

    @pytest.mark.unit
    def test_untagged_and_clean(self, monkeypatch):
        _stub_git(monkeypatch, commit="abc1234", tags=[], dirty="")
        assert _compute_version("0.1.1") == "0.1.1-abc1234"

    @pytest.mark.unit
    def test_untagged_and_dirty(self, monkeypatch):
        _stub_git(monkeypatch, commit="abc1234", tags=[], dirty=" M app/x.py")
        assert _compute_version("0.1.1") == "0.1.1-abc1234-dirty"


class TestTagMatching:
    """Only the tag for *this* release number counts as being on a release."""

    @pytest.fixture(autouse=True)
    def _no_stamp(self, monkeypatch):
        monkeypatch.delenv("APP_BUILD_SHA", raising=False)

    @pytest.mark.unit
    @pytest.mark.parametrize("tag", ["v0.1.1", "0.1.1"])
    def test_both_spellings_of_the_release_tag_match(self, monkeypatch, tag):
        _stub_git(monkeypatch, commit="6d15bde", tags=[tag], dirty="")
        assert _compute_version("0.1.1") == "0.1.1"

    @pytest.mark.unit
    @pytest.mark.parametrize("tag", ["nightly", "v0.1.1-rc1", "v0.1.10", "v0.1.0"])
    def test_other_tags_do_not_match(self, monkeypatch, tag):
        _stub_git(monkeypatch, commit="abc1234", tags=[tag], dirty="")
        assert _compute_version("0.1.1") == "0.1.1-abc1234"

    @pytest.mark.unit
    def test_release_tag_among_several_matches(self, monkeypatch):
        _stub_git(monkeypatch, commit="6d15bde", tags=["nightly", "v0.1.1"], dirty="")
        assert _compute_version("0.1.1") == "0.1.1"


class TestGitUnavailable:
    """Every way of not getting an answer collapses to the bare release number."""

    @pytest.fixture(autouse=True)
    def _no_stamp(self, monkeypatch):
        monkeypatch.delenv("APP_BUILD_SHA", raising=False)

    @pytest.mark.unit
    def test_not_a_repository(self, monkeypatch):
        _stub_git(monkeypatch, commit=None, tags=None, dirty=None)
        assert _compute_version("0.1.1") == "0.1.1"

    @pytest.mark.unit
    def test_no_commit_means_no_dirty_marker_either(self, monkeypatch):
        """If the commit is unknowable, so is everything else. Do not guess."""
        _stub_git(monkeypatch, commit=None, tags=[], dirty=" M app/x.py")
        assert _compute_version("0.1.1") == "0.1.1"

    @pytest.mark.unit
    def test_empty_commit_output_is_no_answer(self, monkeypatch):
        _stub_git(monkeypatch, commit="", tags=[], dirty="")
        assert _compute_version("0.1.1") == "0.1.1"

    @pytest.mark.unit
    def test_unanswerable_tag_and_dirty_checks_still_report_the_commit(self, monkeypatch):
        """A commit but no other answers: report the commit, claim nothing more."""
        _stub_git(monkeypatch, commit="abc1234", tags=None, dirty=None)
        assert _compute_version("0.1.1") == "0.1.1-abc1234"


class TestGitHelper:
    """_git against the real subprocess boundary -- the stub cannot test this.

    This is the test for FR-008: version resolution must never raise into a page
    render. Every failure below returns None instead of propagating.
    """

    @pytest.mark.unit
    def test_successful_call_returns_stripped_stdout(self):
        assert _git("rev-parse", "--show-toplevel") is not None

    @pytest.mark.unit
    def test_nonzero_exit_returns_none(self):
        assert _git("cat-file", "-e", "0" * 40) is None

    @pytest.mark.unit
    def test_unknown_subcommand_returns_none(self):
        assert _git("no-such-subcommand-for-git") is None

    @pytest.mark.unit
    def test_missing_git_binary_returns_none(self, monkeypatch):
        def boom(*args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory: 'git'")

        monkeypatch.setattr(subprocess, "run", boom)
        assert _git("rev-parse", "HEAD") is None

    @pytest.mark.unit
    def test_hanging_git_returns_none(self, monkeypatch):
        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=5)

        monkeypatch.setattr(subprocess, "run", boom)
        assert _git("rev-parse", "HEAD") is None


class TestReportedVersionShape:
    """Whatever the environment this suite runs in, __version__ is well formed."""

    @pytest.mark.unit
    def test_module_version_starts_with_the_release_number(self):
        assert version_module.__version__.startswith(RELEASE_VERSION)

    @pytest.mark.unit
    def test_module_version_matches_the_documented_grammar(self):
        import re

        assert re.fullmatch(
            r"\d+\.\d+\.\d+(-[0-9a-f]{7})?(-dirty)?", version_module.__version__
        ), version_module.__version__
