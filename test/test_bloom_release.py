import os.path
import pytest

from contextlib import chdir
from pathlib import Path
from unittest.mock import Mock

from rosdistro_bloom.bloom_repository import GitReleaseRepository


@pytest.fixture
def fixture_path():
    return Path(os.path.abspath(__file__)).parent / 'fixtures'


@pytest.fixture
def rosdistro():
    def _rosdistro(name, repositories=None):
        mock = Mock()
        mock.name = name
        mock.repositories = dict()
        for name, spec in repositories.items():
            mock.repositories[name] = Mock()
            mock.repositories[name].release_repository = Mock()
            mock.repositories[name].release_repository.type = spec["type"]
            mock.repositories[name].release_repository.url = spec["url"]
            mock.repositories[name].release_repository.version = spec["version"]
        return mock
    return _rosdistro


def test_bloom_release_same_distro(tmp_path, rosdistro):
    source_dist = rosdistro("rolling", {"apriltag": {"type": "git", "version": "3.4.2-1", "url": "https://github.com/rosdistro-bloom-testing/apriltag-release.git"}})
    dest_dist = rosdistro("rolling", {"apriltag": {"type": "git", "version": "3.4.2-1", "url": "https://github.com/rosdistro-bloom-testing/apriltag-release.git"}})
    with chdir(tmp_path):
        with GitReleaseRepository("apriltag", source_dist, dest_dist).clone() as bloom_repo:
            bloom_repo.bloom_release()
            assert dest_dist.repositories["apriltag"].release_repository.version == "3.4.2-5"


def test_bloom_release_same_distro_patches():
    pass


def test_bloom_release_new_distro_no_patches():
    pass


def test_bloom_release_new_distro_patches():
    pass
