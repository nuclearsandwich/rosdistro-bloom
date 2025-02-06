import copy
import os
import shutil
import subprocess

from contextlib import contextmanager, chdir
from pathlib import Path
from functools import cached_property

from bloom.git import branch_exists
from rosdistro_bloom.bloom_tracks import read_tracks_file, write_tracks_file
from rosdistro_bloom.git import ls_remote_branches as git_ls_remote_branches


class GitReleaseRepository:
    def __init__(self, repo_name, source_distribution, dest_distribution):
        self.source_dist = source_distribution
        self.dest_dist = dest_distribution
        self.repo_name = repo_name

    @cached_property
    def release_repo(self):
        name = self.url.split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name

    @cached_property
    def url(self):
        return self.dest_dist.repositories[self.repo_name].release_repository.url

    @contextmanager
    def clone(self):
        if not Path(self.release_repo).is_dir():
            subprocess.check_call(["git", "clone", self.url])
        with chdir(self.release_repo):
            self._in_clone = True
            yield self
            self._in_clone = None

    def copy_ignore_file(self):
        # Copy a bloom .ignored file from source to target distro.
        shutil.copyfile(f"{self.source_dist.name}.ignored", f"{self.dest_dist.name}.ignored")
        with open(".git/rosdistromigratecommitmsg", "w") as f:
            f.write(f"Propagate {source} ignore file to {dest}.")
        subprocess.check_call(["git", "add", f"{dest}.ignored"])
        subprocess.check_call(["git", "commit", "-F", ".git/rosdistromigratecommitmsg"])

    def copy_release_track(self):
        source = self.source_dist.name
        dest = self.dest_dist.name
        tracks = read_tracks_file()
        if not tracks["tracks"].get(source):
            raise ValueError(f"Source track `{source}` is missing in release repository")
        tracks["tracks"][dest] = copy.deepcopy(tracks["tracks"][source])
        tracks["tracks"][dest]["ros_distro"] = dest
        write_tracks_file(tracks, f"Copy {source} track to {dest} with rosdistro_bloom.")

    def copy_refs(self):
        source = self.source_dist.name
        dest = self.dest_dist.name
        for ref in git_ls_remote_branches(f"*{source}*"):
            obj, ref = ref.split("\t")
            ref = ref[11:]  # strip 'refs/heads/'
            newref = ref.replace(source, dest)
            if not branch_exists(newref):
                # TODO: Add base support to bloom.git.create_branch()
                subprocess.check_call(["git", "branch", newref, obj])

    def bloom_release(self):
        source = self.source_dist.name
        dest = self.dest_dist.name
        source_version, source_inc = self.source_dist.repositories[self.repo_name].release_repository.version.split("-")
        tracks = read_tracks_file()
        release_track = tracks["tracks"][dest]
        if release_track["version"] in [":{ask}", ":{auto}"]:
            release_track["version_saved"] = release_track["version"]
            release_track["version"] = source_version
            write_tracks_file(tracks, f"Update {dest} track to release the same version as the source distribution.")
        if release_track["release_tag"] == ":{ask}" and "last_release" in release_track:
            release_track["release_tag_saved"] = release_track["release_tag"]
            release_track["release_tag"] = release_track["last_release"]
            write_tracks_file(tracks, f"Update {dest} track to release exactly last-released tag.")

        # Update release increment for the upcoming release.
        # We increment whichever is greater between the source distribution's
        # release increment and the release increment in the bloom track since
        # there may be releases that were not committed to the source
        # distribution.
        # This heuristic does not fully cover situations where the version in
        # the source distribution and the version in the release track differ.
        # In that case it is still possible for this tool to overwrite a
        # release increment if the greatest increment of the source version is
        # not in the source distribution and does not match the version
        # currently in the release track.
        release_inc = str(max(int(source_inc), int(release_track["release_inc"])) + 1)

        subprocess.check_call(["git", "bloom-release", "--non-interactive", "--release-increment", release_inc, "--unsafe", dest], stdin=subprocess.DEVNULL, env=os.environ)
        subprocess.check_call(["git", "push", "origin", "--all", "--force"])
        subprocess.check_call(["git", "push", "origin", "--tags", "--force"])
        subprocess.check_call(["git", "checkout", "master"])

        # Re-read tracks.yaml after release.
        tracks = read_tracks_file()
        release_track = tracks["tracks"][dest]
        if "version_saved" in release_track:
            release_track["version"] = release_track["version_saved"]
            del release_track["version_saved"]
            write_tracks_file(tracks, f"Restore saved version for {dest} track.")
        if "release_tag_saved" in release_track:
            release_track["release_tag"] = release_track["release_tag_saved"]
            del release_track["release_tag_saved"]
            write_tracks_file(tracks, f"Restore saved version and tag for {dest} track.")
        dest_release_spec = self.dest_dist.repositories[self.repo_name].release_repository
        new_release_inc = str(int(release_track["release_inc"]))
        ver, _inc = dest_release_spec.version.split("-")
        dest_release_spec.version = "-".join([ver, new_release_inc])
