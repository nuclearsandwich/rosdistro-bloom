import argparse
import os
import os.path
import subprocess
import tempfile

from github import GithubException


from rosdistro_bloom.github import ReleaseOrg, can_release_repo, github_client
from rosdistro_bloom.rosdistro import RosdistroIndexDirectory
from rosdistro_bloom.bloom_repository import GitReleaseRepository


def main():
    parser = argparse.ArgumentParser(description="Import packages from one rosdistro into another one.")
    parser.add_argument("--source", required=True, help="The source rosdistro name")
    parser.add_argument(
        "--source-ref",
        required=True,
        help="The git version for the source. Used to retry failed imports without bumping versions.",
    )
    parser.add_argument("--dest", required=True, help="The destination rosdistro name")
    # TODO: Change behavior to skip copying to release org in most cases.
    parser.add_argument(
        "--release-org",
        required=True,
        help="The organization containing release repositories",
    )

    args = parser.parse_args()
    release_org = ReleaseOrg(args.release_org, github_client())

    with RosdistroIndexDirectory(os.getcwd()) as rosdistro_index_dir:
        source_distribution = rosdistro_index_dir.get_source_distribution(args.source, args.source_ref)
        dest_distribution = rosdistro_index_dir.get_dest_distribution(args.dest)
        new_repositories, repositories_to_retry = rosdistro_index_dir.copy_source_repos_to_dest(
            source_distribution, dest_distribution
        )

    for repo_name in new_repositories + repositories_to_retry:
        if not can_release_repo(dest_distribution.repositories[repo_name].release_repository):
            raise RuntimeError(f"Unable to release {repo_name} unless it is a Git repository")
        if not release_org.contains_repo(dest_distribution[repo_name].release_repository.url):
            # TODO make this error non-fatal again.
            raise RuntimeError(f"{repo_name} is not currently present in release org. Set up release repository first?")

    print(f"Found {len(new_repositories)} new repositories to release:", new_repositories)
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
    rosdistro_index_dir.write_distribution_file(dest_distribution)

    repositories_bloomed = []
    repositories_with_errors = []

    workdir = tempfile.mkdtemp()
    os.chdir(workdir)
    os.environ["ROSDISTRO_INDEX_URL"] = rosdistro_index_dir.index_url
    os.environ["BLOOM_SKIP_ROSDEP_UPDATE"] = "1"

    # This call to update rosdep is critical because we're setting
    # ROSDISTRO_INDEX_URL above and also suppressing the automatic
    # update in Bloom itself.
    subprocess.check_call(["rosdep", "update"])

    # TODO chdir tempdir
    for repo_name in sorted(new_repositories + repositories_to_retry):
        try:
            print("Releasing repo:", repo_name)
            with GitReleaseRepository(repo_name, source_distribution, dest_distribution).clone() as bloom_repo:
                if source_distribution.name != dest_distribution.name:
                    bloom_repo.copy_ignore_file()
                    bloom_repo.copy_release_track(source_distribution.name, dest_distribution.name)
                    bloom_repo.copy_refs(source_distribution.name, dest_distribution.name)

                bloom_repo.bloom_release()
            repositories_bloomed.append(repo_name)

        except (subprocess.CalledProcessError, ValueError, GithubException) as e:
            repositories_with_errors.append((repo_name, e))

    for dest_repo in sorted(new_repositories + repositories_to_retry):
        if dest_repo not in repositories_bloomed:
            print(f"{dest_repo} was not bloomed! Removing the release version,")
            dest_distribution.repositories[dest_repo].release_repository.version = None

    rosdistro_index_dir.write_distribution_file(dest_distribution)

    print(
        f"Had {len(repositories_with_errors)} repositories with errors:",
        repositories_with_errors,
    )
