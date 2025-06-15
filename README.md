# `commit-action`

Action which performs a Git commit.
The action allows either pushing to an existing branch, or creating a new branch and raising a PR for that new branch.
Importantly, this uses the GitHub API, and so is signed wherever possible.

# Behaviour

We expect you to have applied some diff, unstaged, to the repository, before you invoke this action.
Then we'll essentially perform `git diff` and create a commit with that diff applied against the currently-checked-out commit, and (if the diff was nonempty) we either push the new commit to an existing branch, or we raise a pull request against the repository's default branch.

As of this writing, *we ignore untracked files*.
You should explicitly `git add --intent-to-add` any untracked files you want to push, before invoking this action.

# Required inputs

## `bearer-token`

You must supply a token with write access to the GitHub API.
We require at least the following permissions (I think; it *may* be possible to use a subset of these, but I haven't checked):

* `Actions`: read and write.
* `Contents`: read and write.
* `Pull requests`: read and write.

If you're using a GitHub App to run your workflow, you can obtain such a token in your Actions file as follows:

```yaml
- name: Create token
  id: generate-token
  uses: actions/create-github-app-token@v1
  with:
    # GitHub recommends using client ID, but they don't actually
    # let you provision one this way
    # https://github.com/actions/create-github-app-token/issues/136
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}

- name: Raise PR
  with:
    bearer-token: ${{ steps.generate-token.outputs.token }}
  # ...
```

Here, I've previously defined `APP_ID` and `APP_PRIVATE_KEY` as [repository secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions#creating-secrets-for-a-repository) in my repo settings.
Their contents are an [app ID](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation#using-an-installation-access-token-to-authenticate-as-an-app-installation) and an [app private key](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps#about-private-keys-for-github-apps) respectively.

## `pr-title`

You must supply the string title of any pull requests to be raised.

## `branch-name`

We raise pull requests using an auto-generated branch name with this prefix; or, in "push to an existing branch" mode, this is the name of the branch to push to.

# Optional inputs

## `pull-request-body`

We raise new pull requests using an auto-generated description.
You can customise this description by setting this to some Markdown.
(Don't set this if you're in push-to-existing-branch mode.)

## `commit-message`

You can customise the commit message of the new commit we make by setting this.

## `target-repo`

In push-to-existing-branch mode only, set this to override the repo on which the `branch-name` is to be found.
(By default, we use the base repo into which the PR is being made.)

# Outputs

## In create-new-PR mode

We set `pull-request-number` on success, to the integer ID of the pull request (so a PR visible at `https://github.com/Org/Repo/pull/135` would have this value set to `135`).
You can therefore check whether the PR was raised:

```yaml
- id: cpr
  name: Create pull request
  uses: Smaug123/commit-action
  with:
    pr-title: My fancy automated PR
    bearer-token: ${{ steps.generate-token.outputs.token }}

- name: Do something with the PR
  # Skip if we didn't raise a PR (e.g. because there was no diff)
  if: ${{ steps.cpr.outputs.pull-request-number }}
  uses: org/some-other-image
  with:
    token: ${{ steps.generate-token.outputs.token }}
    # Use the pull request number, e.g. 135
    that-step-wants-input: ${{ steps.cpr.outputs.pull-request-number }}
```

## In push-to-existing-PR mode

We set `commit-sha` on success, to the SHA we pushed.
