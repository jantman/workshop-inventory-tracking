"""
The extension's declared version and the application's are one string (FR-024).

A test rather than a build step, deliberately. A step that stamped the manifest
from ``pyproject.toml`` would leave the checked-in manifest permanently wrong,
and the whole install story is "load this directory unpacked" -- which has to
work without running anything first. A test instead fails loudly, in CI, on the
pull request that introduced the mismatch.

Both files are read here. Hardcoding the number would make this test agree with
itself and with nothing else.
"""

import json
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
MANIFEST = REPO_ROOT / 'extension' / 'manifest.json'
PYPROJECT = REPO_ROOT / 'pyproject.toml'


@pytest.fixture
def manifest():
    return json.loads(MANIFEST.read_text())


@pytest.mark.unit
class TestTheVersionsAgree:
    def test_the_manifest_declares_the_application_s_version(self, manifest):
        """FR-024. A release ships both by the same act, or it ships a mismatch."""
        project = tomllib.loads(PYPROJECT.read_text())['project']['version']

        assert manifest['version'] == project

    def test_the_declared_version_is_one_chrome_accepts(self, manifest):
        """One to four dot-separated integers, each 0-65535.

        The project's scheme fits without translation, which is why nothing
        converts between the two. If a version ever appears that does not fit --
        a ``2.1.0rc1``, say -- this is where that is found, rather than at
        install time on the operator's machine.
        """
        parts = manifest['version'].split('.')

        assert 1 <= len(parts) <= 4, manifest['version']
        for part in parts:
            assert part.isdigit(), manifest['version']
            assert 0 <= int(part) <= 65535, manifest['version']


@pytest.mark.unit
class TestTheManifestAsksForNothingElse:
    """The permission list is on the install screen, and a short one gets read.

    Asserted as an exact set rather than a subset: the cost of an extra
    permission is paid by the person deciding whether to install, so one
    arriving unnoticed is exactly the failure worth a test (048 research.md §8).
    """

    def test_the_permissions_are_the_four_that_are_load_bearing(self, manifest):
        assert set(manifest['permissions']) == {
            'scripting', 'storage', 'contextMenus', 'activeTab',
        }

    def test_no_host_permissions_are_declared(self, manifest):
        """``activeTab`` grants injection only when the operator asks.

        Host permissions would grant standing access to Amazon and McMaster, and
        would not help the readers' own fetches -- host permissions do not lift
        CORS for a content script.
        """
        assert 'host_permissions' not in manifest

    def test_nothing_runs_until_the_operator_asks(self, manifest):
        """No declared content script, so no reader runs on an ordinary visit."""
        assert 'content_scripts' not in manifest

    def test_every_file_the_manifest_names_exists(self, manifest):
        """A manifest naming a file that is not there fails at install time."""
        named = [
            manifest['background']['service_worker'],
            manifest['options_page'],
            *manifest['icons'].values(),
            *manifest['action']['default_icon'].values(),
        ]

        missing = [name for name in named if not (MANIFEST.parent / name).is_file()]
        assert not missing, missing
