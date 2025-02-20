import subprocess


# TODO move this function to bloom.git and update the dependency.
# It's here for now to keep progress moving forward.
def ls_remote_branches(remote="origin", pattern=None):
    cmd = ["git", "ls-remote", "--branches", remote]
    if pattern is not None:
        cmd.append(pattern)
    remote_branches = subprocess.check_output(cmd, universal_newlines=True)
    return [line for line in remote_branches.splitlines() if line != ""]
