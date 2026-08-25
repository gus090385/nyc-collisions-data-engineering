# Git Command Reference

A running reference of every Git/GitHub CLI command used in this project, with a brief explanation of what each one does. New commands will be appended here as the project progresses.

---

## Setup & Configuration

```
git --version
```
Checks that Git is installed and shows the installed version. Used to verify installation.

```
gh --version
```
Checks that GitHub CLI is installed and shows the installed version.

```
gh auth login
```
Authenticates your terminal with your GitHub account (via browser, no password needed). Required before you can push/pull to private repos or create repos from the command line.

```
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```
Sets the name and email attached to every commit you make. `--global` means it applies to all repos on your machine, not just this one.

---

## Starting a Repository

```
git init
```
Initializes a new, empty Git repository in the current folder (creates a hidden `.git` folder that tracks all history/changes). Run once per project, at the very start.

---

## Checking Status

```
git status
```
Shows the current state of your working folder: which files are untracked (new), modified, or staged for commit. This is the command you run constantly to see "what's going on" before deciding what to do next.

```
git log
```
Shows the commit history — a list of past commits with their hash (unique ID), author, date, and message. Press `q` to exit if it opens in a scrollable pager view.

---

## Staging & Committing

```
git add .
```
Stages **all** changed/new files in the current folder (and subfolders) so they're ready to be committed. The `.` means "everything in this directory."

```
git add <filename>
```
Stages a single specific file instead of everything — useful when you only want to commit part of your changes.

```
git commit -m "Your message here"
```
Saves a permanent snapshot (a "commit") of everything currently staged, along with a message describing what changed. The `-m` flag lets you write the message inline instead of opening a text editor.

**Note:** Use plain, straight double quotes (`"`) around the message, typed directly rather than pasted — pasted text sometimes carries "smart quotes" that Command Prompt doesn't parse correctly, causing an `error: switch 'm' requires a value`.

---

## Connecting to GitHub & Pushing

```
gh repo create <repo-name> --public --source=. --remote=origin --push
```
A GitHub CLI shortcut that does four things in one command:
1. Creates a new repository on GitHub.com (here, `--public` makes it publicly visible)
2. Uses the current folder (`--source=.`) as the repo content
3. Links it to your local repo as a remote named `origin`
4. Immediately pushes your existing commit(s) up to GitHub

```
git remote -v
```
Lists the remote repositories linked to your local repo (typically just `origin`), showing the URLs used for fetching and pushing. Used to confirm the GitHub link is set up correctly.

```
git push
```
Uploads your local commits to the linked remote repository (GitHub) so they're visible online. After the first push (done automatically above via `gh repo create ... --push`), future pushes just need `git push` on its own.

---

## Folder/File Management (Windows Command Prompt)

```
mkdir <folder-name>
```
Creates a new folder. **Important:** run one `mkdir` per line/command — pasting multiple `mkdir`/`cd`/`git` commands as one block causes Command Prompt to misread them (it tried to create folders literally named `cd`, `git`, `init` in our case).

```
cd <folder-name>
```
Changes your terminal's current directory into the named folder.

```
rmdir <folder-name>
```
Removes an empty folder. Used to clean up folders accidentally created by a multi-line paste mistake.

```
dir
```
Lists files and folders in the current directory (Windows equivalent of `ls`).

```
dir /a
```
Same as `dir`, but also shows hidden files — needed to confirm dot-files like `.gitignore` actually exist, since Windows Explorer can hide/mislabel them.

---

## Common Gotchas Encountered So Far

| Issue | Cause | Fix |
|---|---|---|
| `mkdir` created folders named `cd`, `git`, `init` | Multi-line command pasted as one block into Command Prompt | Run commands one at a time, pressing Enter after each |
| `.gitignore` downloaded as `.gitignore_6` | Browser auto-renamed to avoid overwriting a duplicate download | Renamed manually via File Explorer back to `.gitignore` |
| `git commit -m "..."` → `error: switch 'm' requires a value` | Pasted text used "smart quotes" instead of straight quotes | Typed the command directly instead of pasting |

---

*This is a living reference — updated as new Git commands are introduced later in the project (branching, `.gitignore` edits, feature branches, etc.).*
