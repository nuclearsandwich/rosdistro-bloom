import os
import shutil
import subprocess

from contextlib import contextmanager, chdir
from pathlib import Path
from functools import cached_property

from rosdistro_bloom.bloom_tracks import read_tracks_file, write_tracks_file

class GitReleaseRepository():
    def __init__(self, source_distribution, dest_distribution, repo_name):
        self.source_dist = source_distribution
        self.dest_dist = dest_distribution
        self.repo_name = repo_name

    @cached_property
    def release_repo(self):
        name = self.url().split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]

    def url(self):
        return self.dest_distribution.repositories[self.repo_name].url

    @contextmanager
    def clone(self):
        if Path(repo_name).is_dir():
            return self
        subpress.check_call(['git', 'clone', self.url()])
        with chdir(self.release_repo):
            yield

    def propagate_ignore_file(self)
        # Copy a bloom .ignored file from source to target distro.
        shutil.copyfile(f"{source}.ignored", f"{dest}.ignored")
        with open(".git/rosdistromigratecommitmsg", "w") as f:
            f.write(f"Propagate {source} ignore file to {dest}.")
        subprocess.check_call(["git", "add", f"{dest}.ignored"])
        subprocess.check_call(
                ["git", "commit", "-F", ".git/rosdistromigratecommitmsg"]
                )




def git_bloom_release():
    pass

def copy_tracks(source):
        dest_track = copy.deepcopy(tracks["tracks"][args.source])
        dest_track["ros_distro"] = args.dest
        tracks["tracks"][args.dest] = dest_track
        ls_remote = subprocess.check_output(
                ["git", "ls-remote", "--heads", "oldorigin", f"*{args.source}*"],
                universal_newlines=True,
                )

def dothething(repo_name, dest_distribution, source_distribution):
    remote_url = release_spec.url
    release_repo = remote_url.split("/")[-1]
    if release_repo.endswith(".git"):
        release_repo = release_repo[:-4]
    subprocess.check_call(["git", "clone", remote_url])
    os.chdir(release_repo)
    tracks = read_tracks_file()

    if not tracks["tracks"].get(args.source):
        raise ValueError("Repository has not been released.")

    if release_repo not in org_release_repos:
    new_release_repo_url = (
            f"https://github.com/{args.release_org}/{release_repo}.git"
            )
    subprocess.check_call(["git", "remote", "rename", "origin", "oldorigin"])
    subprocess.check_call(
            ["git", "remote", "set-url", "--push", "oldorigin", "no_push"]
            )
    subprocess.check_call(
            ["git", "remote", "add", "origin", new_release_repo_url]
            )

    if args.source != args.dest:
        # Copy a bloom .ignored file from source to target distro.
        if os.path.isfile(f"{args.source}.ignored"):
            propagate_ignore_file(args.source, args.dest)

        # Copy the source track to the new destination.
        for line in ls_remote.split("\n"):
            if line == "":
                continue
            obj, ref = line.split("\t")
            ref = ref[11:]  # strip 'refs/heads/'
            newref = ref.replace(args.source, args.dest)
            subprocess.check_call(["git", "branch", newref, obj])
            if newref.startswith("patches/"):
                # Update parent in patch configs. Without this update the
                # patches will be rebased out when git-bloom-release is
                # called because the configured parent won't match the
                # expected source branch.
                config = get_patch_config(newref)
                config["parent"] = config["parent"].replace(
                        args.source, args.dest
                        )
                set_patch_config(newref, config)
        # Check for a release repo url in the track configuration
        if "release_repo_url" in dest_track:
            dest_track["release_repo_url"] = None
        write_tracks_file(
                tracks,
                f"Copy {args.source} track to {args.dest} with migrate-rosdistro.py.",
                )
    else:
        dest_track = tracks["tracks"][args.dest]

    # Configure next release to re-release previous version into the
    # destination.  A version value of :{ask} will fail due to
    # interactivity and :{auto} may result in a previously unreleased tag
    # on the development branch being released for the first time.
    if dest_track["version"] in [":{ask}", ":{auto}"]:
        # Override the version for this release to guarantee the same version from our
        # source distribution is released.
        dest_track["version_saved"] = dest_track["version"]
        source_version, source_inc = source_distribution.repositories[
                repo_name
                ].release_repository.version.split("-")
        dest_track["version"] = source_version
        write_tracks_file(
                tracks,
                f"Update {args.dest} track to release the same version as the source distribution.",
                )

    if dest_track["release_tag"] == ":{ask}" and "last_release" in dest_track:
        # Override the version for this release to guarantee the same version is released.
        dest_track["release_tag_saved"] = dest_track["release_tag"]
        dest_track["release_tag"] = dest_track["last_release"]
        write_tracks_file(
                tracks,
                f"Update {args.dest} track to release exactly last-released tag.",
                )

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
    release_inc = str(max(int(source_inc), int(dest_track["release_inc"])) + 1)

    # Bloom will not run with multiple remotes.
    subprocess.check_call(["git", "remote", "remove", "oldorigin"])
    subprocess.check_call(
            [
                "git",
                "bloom-release",
                "--non-interactive",
                "--release-increment",
                release_inc,
                "--unsafe",
                args.dest,
                ],
            stdin=subprocess.DEVNULL,
            env=os.environ,
            )
    subprocess.check_call(["git", "push", "origin", "--all", "--force"])
    subprocess.check_call(["git", "push", "origin", "--tags", "--force"])
    subprocess.check_call(["git", "checkout", "master"])

    # Re-read tracks.yaml after release.
    tracks = read_tracks_file()
    dest_track = tracks["tracks"][args.dest]
    if "version_saved" in dest_track:
        dest_track["version"] = dest_track["version_saved"]
        del dest_track["version_saved"]
        write_tracks_file(
                tracks, f"Restore saved version for {args.dest} track."
                )
    if "release_tag_saved" in dest_track:
        dest_track["release_tag"] = dest_track["release_tag_saved"]
        del dest_track["release_tag_saved"]
        write_tracks_file(
                tracks, f"Restore saved version and tag for {args.dest} track."
                )
    new_release_track_inc = str(int(tracks["tracks"][args.dest]["release_inc"]))
    release_spec.url = new_release_repo_url

    ver, _inc = release_spec.version.split("-")
    release_spec.version = "-".join([ver, new_release_track_inc])
    repositories_bloomed.append(repo_name)
    subprocess.check_call(["git", "push", "origin", "master"])
