import copy
import os
import yaml

from contextlib import AbstractContextManager
from functools import cached_property
from pathlib import Path

from bloom.git import show as git_show
from rosdistro import DistributionFile, get_distribution_file, get_index
from rosdistro.writer import yaml_from_distribution_file


class RosdistroIndexDirectory(AbstractContextManager):
    def __init__(self, directory: str | Path):
        if type(directory) is str:
            directory = Path(directory)
        directory = directory.absolute()
        if not directory.is_dir():
            raise RuntimeError(f"{directory} is not a directory")
        if not (directory / "index-v4.yaml").exists():
            raise RuntimeError(f"{directory} does not appear to be a rosdistro index directory (no index-v4.yaml file found).")
        if not (directory / ".git").is_dir():
            raise RuntimeError(f"{directory} is not a git repository so source distribution cannot be retrieved from git ref")
        self.directory = directory

    def __enter__(self):
        if self.oldwd is not None:
            raise RuntimeError("Directory context already entered!")

        cwd = Path(os.getcwd())
        self.oldwd = cwd
        os.chdir(self.directory)
        return self

    def __exit__(self):
        os.chdir(self.oldwd)
        self.oldwd = None
        return None

    @cached_property
    def index_url(self):
        return f"file://{self.directory}/index-v4.yaml"

    @cached_property
    def index(self):
        return get_index(self.index_url)

    def get_source_distribution(self, distribution_name, git_ref):
        index_yaml = yaml.safe_load(open(self.directory / "index-v4.yaml", "r"))
        if len(index_yaml["distributions"][distribution_name]["distribution"]) != 1:
            raise RuntimeError("Source distribution must have a single distribution file.")

        # There is a possibility that the source_ref has a different distribution file
        # layout. Check that they match.
        source_ref_index_yaml = yaml.safe_load(git_show(git_ref, "index-v4.yaml"))
        if (
            source_ref_index_yaml["distributions"][distribution_name]["distribution"]
            != index_yaml["distributions"][distribution_name]["distribution"]
        ):
            raise RuntimeError("The distribution file layout has changed between the source ref and now.")

        source_distribution_filename = index_yaml["distributions"][distribution_name]["distribution"][0]

        # Fetch the source distribution file from the exact point in the repository history requested.
        source_distfile_data = yaml.safe_load(git_show(git_ref, source_distribution_filename))
        return DistributionFile(distribution_name, source_distfile_data)

    def get_dest_distribution(self, distribution_name):
        # Check local rosdistro index.
        index_yaml = yaml.safe_load(open(self.directory / "index-v4.yaml", "r"))
        if len(index_yaml["distributions"][distribution_name]["distribution"]) != 1:
            raise RuntimeError("Source distribution must have a single distribution file.")
        return get_distribution_file(self.index, distribution_name)

    def write_distribution_file(self, dist: DistributionFile):
        with open(self.directory / dist.name / "distribution.yaml", "w") as f:
            f.write(yaml_from_distribution_file(dist))

    def copy_source_repos_to_dest(self, source: DistributionFile, dest: DistributionFile):
        new_repos = []
        retry_repos = []
        for repo_name, repo_data in sorted(source.repositories.items()):
            if repo_name not in dest.repositories:
                dest_repo_data = copy.deep_copy(repo_data)
                if dest_repo_data.release_repository:
                    new_repos.append(repo_name)
                    release_tag = dest_repo_data.release_repository.tags["release"]
                    release_tag = release_tag.replace(source.name, dest.name)
                    dest_repo_data.release_repository.tags["release"] = release_tag
                dest.repositories[repo_name] = dest_repo_data
            elif (
                    dest.repositories[repo_name].release_repository is not None
                    and dest.repositories[repo_name].release_repository.version is None
            ):
                dest.repositories[repo_name].release_repository.version = repo_data.release_repository.version
                retry_repos.append(repo_name)
            else:
                # Nothing to do if the repository is already released in dest.
                pass
        return new_repos, retry_repos
