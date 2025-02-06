import os.path
import pytest

from contextlib import chdir
from pathlib import Path
from unittest.mock import Mock

from bloom.git import inbranch

from rosdistro_bloom.bloom_repository import GitReleaseRepository


@pytest.fixture(autouse=True)
def rosdistro_url(monkeypatch):
    monkeypatch.setenv("ROSDISTRO_INDEX_URL", "https://raw.githubusercontent.com/rosdistro-bloom-testing/rosdistro/main/index-v4.yaml")


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
    source_dist = rosdistro("rolling", {"testpkg": {"type": "git", "version": "1.0.0-1", "url": "https://github.com/rosdistro-bloom-testing/testpkg-release.git"}})
    dest_dist = rosdistro("rolling", {"testpkg": {"type": "git", "version": "1.0.0-1", "url": "https://github.com/rosdistro-bloom-testing/testpkg-release.git"}})
    with chdir(tmp_path):
        with GitReleaseRepository("testpkg", source_dist, dest_dist).clone() as bloom_repo:
            bloom_repo.bloom_release()
            assert dest_dist.repositories["testpkg"].release_repository.version == "1.0.0-2"


def test_bloom_release_same_distro_patches(tmp_path, rosdistro):
    source_dist = rosdistro("rolling", {"testpkg": {"type": "git", "version": "1.0.0-2", "url": "https://github.com/rosdistro-bloom-testing/patchpkg-release.git"}})
    dest_dist = rosdistro("rolling", {"testpkg": {"type": "git", "version": "1.0.0-2", "url": "https://github.com/rosdistro-bloom-testing/patchpkg-release.git"}})
    with chdir(tmp_path):
        with GitReleaseRepository("testpkg", source_dist, dest_dist).clone() as bloom_repo:
            bloom_repo.bloom_release()
            assert dest_dist.repositories["testpkg"].release_repository.version == "1.0.0-3"
            with inbranch("release/rolling/testpkg/1.0.0-3"):
                assert (tmp_path / bloom_repo.release_repo / "releasepatch").is_file()
            with inbranch("debian/ros-rolling-testpkg_1.0.0-2_noble"):
                assert (tmp_path / bloom_repo.release_repo / "releasepatch").is_file()
                assert (tmp_path / bloom_repo.release_repo / "debianpatch").is_file()
            with inbranch("rpm/ros-rolling-testpkg-1.0.0-2_9"):
                assert (tmp_path / bloom_repo.release_repo / "releasepatch").is_file()
                assert (tmp_path / bloom_repo.release_repo / "rpmpatch").is_file()


def test_bloom_release_new_distro_no_patches(tmp_path, rosdistro):
    source_dist = rosdistro("rolling", {"testpkg": {"type": "git", "version": "1.0.0-1", "url": "https://github.com/rosdistro-bloom-testing/testpkg-release.git"}})
    dest_dist = rosdistro("jazzy", {"testpkg": {"type": "git", "version": "1.0.0-1", "url": "https://github.com/rosdistro-bloom-testing/testpkg-release.git"}})
    with chdir(tmp_path):
        with GitReleaseRepository("testpkg", source_dist, dest_dist).clone() as bloom_repo:
            bloom_repo.copy_release_track()
            bloom_repo.copy_refs()
            with inbranch("release/jazzy/testpkg"):
                assert Path("package.xml").is_file()
            bloom_repo.bloom_release()
            assert dest_dist.repositories["testpkg"].release_repository.version == "1.0.0-2"


@pytest.mark.xfail
def test_bloom_release_new_distro_patches(tmp_path, rosdistro):
    source_dist = rosdistro("rolling", {"testpkg": {"type": "git", "version": "1.0.0-2", "url": "https://github.com/rosdistro-bloom-testing/patchpkg-release.git"}})
    dest_dist = rosdistro("jazzy", {"testpkg": {"type": "git", "version": "1.0.0-2", "url": "https://github.com/rosdistro-bloom-testing/patchpkg-release.git"}})
    with chdir(tmp_path):
        with GitReleaseRepository("testpkg", source_dist, dest_dist).clone() as bloom_repo:
            bloom_repo.copy_release_track()
            bloom_repo.copy_refs()
            bloom_repo.bloom_release()
            assert dest_dist.repositories["testpkg"].release_repository.version == "1.0.0-3"
            with inbranch("release/jazzy/testpkg/1.0.0-3"):
                assert (tmp_path / bloom_repo.release_repo / "releasepatch").is_file()
            with inbranch("debian/ros-jazzy-testpkg_1.0.0-3_noble"):
                assert (tmp_path / bloom_repo.release_repo / "releasepatch").is_file()
                assert (tmp_path / bloom_repo.release_repo / "debianpatch").is_file()
            with inbranch("rpm/ros-jazzy-testpkg-1.0.0-3_9"):
                assert (tmp_path / bloom_repo.release_repo / "releasepatch").is_file()
                assert (tmp_path / bloom_repo.release_repo / "rpmpatch").is_file()
