import subprocess
import sys

import yaml

from bloom.git import inbranch, show


# These functions are adapted from Bloom's internal 'get_tracks_dict_raw' and
# 'write_tracks_dict_raw' functions.  We cannot use them directly since they
# make assumptions about the release repository that are not true during the
# manipulation of the release repository for this script.
def read_tracks_file():
    tracks_yaml = show("master", "tracks.yaml")
    if tracks_yaml:
        return yaml.safe_load(tracks_yaml)
    else:
        raise ValueError("repository is missing tracks.yaml in master branch.")


@inbranch("master")
def write_tracks_file(tracks, commit_msg=None):
    if commit_msg is None:
        commit_msg = f"Update tracks.yaml from {sys.argv[0]}."
    with open("tracks.yaml", "w") as f:
        f.write(yaml.safe_dump(tracks, indent=2, default_flow_style=False))
    with open(".git/rosdistromigratecommitmsg", "w") as f:
        f.write(commit_msg)
    subprocess.check_call(["git", "add", "tracks.yaml"])
    subprocess.check_call(["git", "commit", "-F", ".git/rosdistromigratecommitmsg"])
