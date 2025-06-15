import datetime
import time
import subprocess
import requests
import os
import base64
from typing import Literal, TypedDict

class TreeEntry(TypedDict):
    path: str
    mode: Literal["100644", "100755", "120000"]
    type: Literal["blob", "tree"]
    sha: str


# GitHub API configuration
GITHUB_API_URL = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY") or ""
if not REPO:
    raise Exception("Supply GITHUB_REPOSITORY env var")
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT") or ""
if not GITHUB_OUTPUT:
    raise Exception("Supply GITHUB_OUTPUT env var")

GITHUB_TOKEN = os.environ.get("BEARER_TOKEN")
if not GITHUB_TOKEN:
    raise Exception("Supply BEARER_TOKEN env var")

COMMIT_MESSAGE = os.environ.get("COMMIT_MESSAGE") or "Automated commit"
BRANCH_NAME = os.environ.get("BRANCH_NAME") or ""
if not BRANCH_NAME:
    raise Exception("Set BRANCH_NAME; this will be used as a prefix for a new branch if we're in PR-creation mode, or verbatim if we're in push-to-existing-branch mode.")


class NewPRInfo(TypedDict):
    pr_title: str
    pr_body: str
    base_branch: str
    source_branch: str


def new_pr_info() -> NewPRInfo | str:
    """
    On failure, returns a human-readable description of why we couldn't construct a NewPRInfo.
    """
    PR_TITLE = os.environ.get("PR_TITLE")
    PULL_REQUEST_BODY = os.environ.get("PULL_REQUEST_BODY") or "Automated pull request."
    DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH")

    if not PR_TITLE:
        return "Supply PR_TITLE env var"
    if not DEFAULT_BRANCH:
        return "Supply DEFAULT_BRANCH env var"

    # BRANCH_NAME treated as a prefix in this mode
    branch_name = BRANCH_NAME + datetime.datetime.fromtimestamp(time.time()).strftime('%Y_%m_%d-%H_%M_%S_%f')

    NEW_PR_INFO = NewPRInfo(pr_title=PR_TITLE, pr_body=PULL_REQUEST_BODY, base_branch=DEFAULT_BRANCH, source_branch=branch_name)

    return NEW_PR_INFO


class ExistingPRInfo(TypedDict):
    target_branch: str
    target_repo: str


def existing_pr_info() -> ExistingPRInfo | str:
    """
    On failure, returns a human-readable description of why we couldn't construct an ExistingPRInfo.
    """
    TARGET_REPO = os.environ.get("TARGET_REPO") or REPO
    if not TARGET_REPO:
        return "Set TARGET_REPO env var, which is the repo where the TARGET_BRANCH is to be found"

    result = ExistingPRInfo(target_branch=BRANCH_NAME, target_repo=TARGET_REPO)

    return result

headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_git_diff():
    """Get the files which have changed in the current repository."""
    return subprocess.check_output(["git", "diff", "--name-only"]).decode("utf-8").splitlines()

def create_blob(content, encoding="utf-8"):
    """Create a blob in the GitHub repository."""
    url = f"{GITHUB_API_URL}/repos/{REPO}/git/blobs"
    data = {
        "content": content,
        "encoding": encoding
    }
    response = requests.post(url, headers=headers, json=data)
    if not response.ok:
        raise Exception(f"bad response: {response}")
    print(f"Blob response: {response.text}")
    return response.json()["sha"]

def create_tree(base_tree: str, changes: list[TreeEntry], repo: str) -> str:
    """Create a new tree with the given changes."""
    url = f"{GITHUB_API_URL}/repos/{repo}/git/trees"
    data = {
        "base_tree": base_tree,
        "tree": changes
    }
    response = requests.post(url, headers=headers, json=data)
    if not response.ok:
        raise Exception(f"bad response: {response}")
    print(f"Tree response: {response.text}")
    return response.json()["sha"]

def create_commit(tree_sha: str, parent_sha: str, message: str, repo: str):
    """Create a new commit."""
    url = f"{GITHUB_API_URL}/repos/{repo}/git/commits"
    data = {
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha]
    }
    print(f"Commit request body: {data}")
    response = requests.post(url, headers=headers, json=data)
    if not response.ok:
        raise Exception(f"bad response: {response}")
    print(f"Commit response: {response.text}")
    json = response.json()
    print(f"Commit: {json}")
    return json["sha"]

def is_executable(filepath: str):
    return os.path.isfile(filepath) and os.access(filepath, os.X_OK)

def get_current_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()

def get_current_tree() -> str:
    return [line for line in subprocess.check_output(["git", "cat-file", "-p", "HEAD"]).decode("utf-8").splitlines() if line.startswith('tree ')][0][5:]

def create_branch(branch_name: str, commit_sha: str) -> None:
    url = f"{GITHUB_API_URL}/repos/{REPO}/git/refs"
    data = {
        "ref": f"refs/heads/{branch_name}",
        "sha": commit_sha
    }
    print(f"Branch creation request body: {data}")
    response = requests.post(url, headers=headers, json=data)
    if not response.ok:
        raise Exception(f"bad response: {response}")
    print(f"Branch creation response: {response.text}")

def create_pull_request(instructions: NewPRInfo) -> tuple[str, int]:
    """Returns the URL of the new PR."""
    url = f"{GITHUB_API_URL}/repos/{REPO}/pulls"
    data = {
        "title": instructions["pr_title"],
        "head": instructions["source_branch"],
        "base": instructions["base_branch"],
        "body": instructions["pr_body"],
        "maintainer_can_modify": True
    }
    print(f"PR creation request body: {data}")
    response = requests.post(url, headers=headers, json=data)
    if not response.ok:
        raise Exception(f"bad response: {response}")
    print(f"PR creation response: {response.text}")
    json = response.json()
    return json["url"], json["number"]

def get_ref_sha(ref: str, repo: str) -> str:
    """Get the SHA of a reference on the remote."""
    url = f"{GITHUB_API_URL}/repos/{repo}/git/ref/heads/{ref}"
    response = requests.get(url, headers=headers)
    if not response.ok:
        raise Exception(f"bad response: {response.text}")
    return response.json()["object"]["sha"]

def get_commit_info(commit_sha: str, repo: str = REPO) -> dict:
    """Get commit information from GitHub API. The response object is the JSON dictionary returned by the repos/{repo}/git/commits/{sha} API endpoint."""
    url = f"{GITHUB_API_URL}/repos/{repo}/git/commits/{commit_sha}"
    response = requests.get(url, headers=headers)
    if not response.ok:
        raise Exception(f"Failed to get commit: {response.text}")
    return response.json()

def main():
    new_info = new_pr_info()
    existing_info = existing_pr_info()
    what_to_do: NewPRInfo | ExistingPRInfo
    if isinstance(new_info, str):
        if isinstance(existing_info, str):
            raise Exception(f"Failed to parse arguments. For creating a new PR, errors as follows:\n{new_info}\n\nFor pushing to an existing branch, errors as follows:\n{existing_info}")
        else:
            what_to_do = existing_info
    else:
        if isinstance(existing_info, str):
            what_to_do = new_info
        else:
            raise Exception("Ambiguous arguments: parsed as both creating a new PR and pushing to an existing one.")

    changed_files = get_git_diff()
    if not changed_files:
        return

    # Create blobs and prepare tree changes
    tree_changes = []
    for file_path in changed_files:
        with open(file_path, "rb") as file:
            contents = base64.b64encode(file.read()).decode('ascii')
        blob_sha = create_blob(contents, encoding="base64")
        if is_executable(file_path):
            mode = "100755"
        else:
            mode = "100644"
        tree_changes.append(TreeEntry({
            "path": file_path,
            "mode": mode,
            "type": "blob",
            "sha": blob_sha
        }))

    base_tree = get_current_tree()

    # Create a new tree
    new_tree_sha = create_tree(base_tree, tree_changes, REPO)
    print(f"Tree: {new_tree_sha}")

    # Create a new commit
    new_commit_sha = create_commit(new_tree_sha, get_current_commit(), COMMIT_MESSAGE, REPO)
    print(f"New commit created: {new_commit_sha}")

    if isinstance(what_to_do, NewPRInfo):
        create_branch(what_to_do["source_branch"], new_commit_sha)
        print(f"Branch created: {what_to_do['source_branch']}")

        url, pr_num = create_pull_request(what_to_do)
        print(f"See PR at: {url}")

        with open(GITHUB_OUTPUT, "a") as output_file:
            output_file.write(f"pull-request-number={pr_num}")
    else:
        # Get the current state of the target branch
        parent_sha = get_ref_sha(what_to_do["target_branch"], REPO)
        parent_commit = get_commit_info(parent_sha, REPO)
        base_tree = parent_commit["tree"]["sha"]

        # Create new tree and commit
        new_tree_sha = create_tree(base_tree, tree_changes, what_to_do["target_repo"])
        new_commit_sha = create_commit(new_tree_sha, parent_sha, COMMIT_MESSAGE, what_to_do["target_repo"])

        # Update the branch
        update_ref(what_to_do["target_branch"], new_commit_sha, what_to_do["target_repo"])
        print(f"Pushed commit {new_commit_sha} to {what_to_do['target_repo']}/{what_to_do['target_branch']}")

        with open(GITHUB_OUTPUT, "a") as output_file:
            output_file.write(f"commit-sha={new_commit_sha}\n")


if __name__ == "__main__":
    main()
