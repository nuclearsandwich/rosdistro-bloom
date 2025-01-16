import argparse
import copy
import os
import os.path
import shutil
import subprocess
import tempfile

from bloom.commands.git.patch.common import get_patch_config, set_patch_config
from bloom.git import show

import github
import yaml

from rosdistro import DistributionFile, get_distribution_file, get_index
from rosdistro.writer import yaml_from_distribution_file

from rosdistro_bloom.bloom_tracks import read_tracks_file, write_tracks_file


def main():
    parser = argparse.ArgumentParser(
        description="Import packages from one rosdistro into another one."
    )
    parser.add_argument("--source", required=True, help="The source rosdistro name")
    parser.add_argument(
        "--source-ref",
        required=True,
        help="The git version for the source. Used to retry failed imports without bumping versions.",
    )
    parser.add_argument("--dest", required=True, help="The destination rosdistro name")
    parser.add_argument(
        "--release-org",
        required=True,
        help="The organization containing release repositories",
    )

    args = parser.parse_args()

    gclient = github.Github(os.environ["GITHUB_TOKEN"])
    release_org = gclient.get_organization(args.release_org)
    org_release_repos = [r.name for r in release_org.get_repos() if r.name]

    if not os.path.isfile("index-v4.yaml"):
        raise RuntimeError("This script must be run from a rosdistro index directory.")
    rosdistro_dir = os.path.abspath(os.getcwd())
    rosdistro_index_url = f"file://{rosdistro_dir}/index-v4.yaml"

    index = get_index(rosdistro_index_url)
    index_yaml = yaml.safe_load(open("index-v4.yaml", "r"))

    if (
        len(index_yaml["distributions"][args.source]["distribution"]) != 1
        or len(index_yaml["distributions"][args.dest]["distribution"]) != 1
    ):
        raise RuntimeError(
            "Both source and destination distributions must have a single distribution file."
        )

    # There is a possibility that the source_ref has a different distribution file
    # layout. Check that they match.
    source_ref_index_yaml = yaml.safe_load(show(args.source_ref, "index-v4.yaml"))
    if (
        source_ref_index_yaml["distributions"][args.source]["distribution"]
        != index_yaml["distributions"][args.source]["distribution"]
    ):
        raise RuntimeError(
            "The distribution file layout has changed between the source ref and now."
        )

    source_distribution_filename = index_yaml["distributions"][args.source][
        "distribution"
    ][0]
    dest_distribution_filename = index_yaml["distributions"][args.dest]["distribution"][
        0
    ]

    # Fetch the source distribution file from the exact point in the repository history requested.
    source_distfile_data = yaml.safe_load(
        show(args.source_ref, source_distribution_filename)
    )
    source_distribution = DistributionFile(args.source, source_distfile_data)

    # Prepare the destination distribution for new bloom releases from the source distribution.
    dest_distribution = get_distribution_file(index, args.dest)
    new_repositories = []
    repositories_to_retry = []
    for repo_name, repo_data in sorted(source_distribution.repositories.items()):
        if repo_name not in dest_distribution.repositories:
            dest_repo_data = copy.deepcopy(repo_data)
            if dest_repo_data.release_repository:
                new_repositories.append(repo_name)
                release_tag = dest_repo_data.release_repository.tags["release"]
                release_tag = release_tag.replace(args.source, args.dest)
                dest_repo_data.release_repository.tags["release"] = release_tag
            dest_distribution.repositories[repo_name] = dest_repo_data
        elif (
            dest_distribution.repositories[repo_name].release_repository is not None
            and dest_distribution.repositories[repo_name].release_repository.version
            is None
        ):
            dest_distribution.repositories[
                repo_name
            ].release_repository.version = repo_data.release_repository.version
            repositories_to_retry.append(repo_name)
        else:
            # Nothing to do if the release is there.
            pass

    print(
        f"Found {len(new_repositories)} new repositories to release:", new_repositories
    )
    print(
        f"Found {len(repositories_to_retry)} repositories to retry:",
        repositories_to_retry,
    )

    # Copy out an optimistic destination distribution file to bloom everything
    # against. This obviates the need to bloom packages in a topological order or
    # do any special handling for dependency cycles between repositories as are
    # known to occur in the ros2/launch repository.  To allow this we must keep
    # track of repositories that fail to bloom and pull their release in a cleanup
    # step.
    with open(dest_distribution_filename, "w") as f:
        f.write(yaml_from_distribution_file(dest_distribution))

    repositories_bloomed = []
    repositories_with_errors = []

    workdir = tempfile.mkdtemp()
    os.chdir(workdir)
    os.environ["ROSDISTRO_INDEX_URL"] = rosdistro_index_url
    os.environ["BLOOM_SKIP_ROSDEP_UPDATE"] = "1"

    # This call to update rosdep is critical because we're setting
    # ROSDISTRO_INDEX_URL above and also suppressing the automatic
    # update in Bloom itself.
    subprocess.check_call(["rosdep", "update"])

    for repo_name in sorted(new_repositories + repositories_to_retry):
        try:
            release_spec = dest_distribution.repositories[repo_name].release_repository
            print("Adding repo:", repo_name)
            if release_spec.type != "git":
                raise ValueError("This script can only handle git repositories.")
            if release_spec.version is None
                raise ValueError(
                        f"{repo_name} is not released in the source distribution (release version is missing or blank)."
                        )
            if release_spec.url.split("/")[-1] not in org_release_repos:
                release_org.create_repo(release_spec.url.split("/")[-1])

        except (subprocess.CalledProcessError, ValueError, github.GithubException) as e:
            repositories_with_errors.append((repo_name, e))
        os.chdir(workdir)

    os.chdir(rosdistro_dir)

    for dest_repo in sorted(new_repositories + repositories_to_retry):
        if dest_repo not in repositories_bloomed:
            print(f"{dest_repo} was not bloomed! Removing the release version,")
            dest_distribution.repositories[dest_repo].release_repository.version = None

    with open(dest_distribution_filename, "w") as f:
        f.write(yaml_from_distribution_file(dest_distribution))

    print(
        f"Had {len(repositories_with_errors)} repositories with errors:",
        repositories_with_errors,
    )
