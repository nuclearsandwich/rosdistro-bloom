import os

import github

from rosdistro import DistributionFile


class ReleaseOrg:
    def __init__(self, org_name, github_client):
        self.name = org_name
        org_repos = github_client.get_organization(org_name).get_repos()
        self.repository_names = [r.name for r in org_repos]

    def contains_repo(self, repository_url):
        if not repository_url.startswith(f"https://github.com/{self.name}/"):
            return False
        repo_name = repository_url.split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        if repo_name in self.repository_names:
            return True
        else:
            return False


def can_release_repo(release_repository_spec):
    if release_repository_spec.type != "git":
        return False


def github_client(token=None):
    if token is None:
        token = os.environ["GITHUB_TOKEN"]
    return github.Github(token)


def check_release_(dist: DistributionFile, org_name: str, repo_names=None):
    errors = []
    gclient = github.Github(os.environ["GITHUB_TOKEN"])
    release_org = gclient.get_organization(org_name)
    org_release_repos = [r.name for r in release_org.get_repos() if r.name]

    if repo_names is None:
        repo_names = dist.repositories.keys()

    for repo_name in sorted(repo_names):
        release_repository = dist.repositories[repo_name].release_repository
        if release_repository is None:
            # Skip repositories with no release information
            continue
        if release_repository.type != "git":
            errors.append(ValueError(f"{repo_name}: This process only supports git repositories."))
            continue
        if release_repository.version is None:
            errors.append(ValueError(f"{repo_name} is not released (release version is missing or blank)."))
            continue
        if not release_repository.url.startswith(f"https://github.com/{org_name}/"):
            errors.append(ValueError(f"{repo_name} has a release repository outside the release org"))

        gh_repo_name = release_repository.url.split("/")[-1]
        if gh_repo_name.endswith(".git"):
            gh_repo_name = gh_repo_name[:-4]
        if gh_repo_name not in org_release_repos:
            errors.append(ValueError(f"{repo_name} does not exist in release org"))
            continue

    return errors
