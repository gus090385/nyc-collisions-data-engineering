# Git & GitHub Setup

This document records how version control was set up for this project, step by step, so it can be reproduced or referenced later.

## 1. GitHub Account
Created a free GitHub account at [github.com](https://github.com) — this hosts the public repository for this portfolio project.

## 2. Install Git for Windows
- Downloaded from [git-scm.com/download/win](https://git-scm.com/download/win)
- Ran the installer with default options, with attention to one key screen:
  - **Adjusting your PATH environment** → selected **"Git from the command line and also from 3rd-party software"** (recommended option) — this makes `git` available from Command Prompt, PowerShell, and Git Bash.
  - **Choosing HTTPS transport backend** → left default: **"Use the native Windows Secure Channel library"**
- Verified install with:
  ```
  git --version
  ```

## 3. Install GitHub CLI (`gh`)
Used the GitHub CLI to handle authentication cleanly (GitHub no longer supports plain password auth for Git operations).

- Installed via `winget`:
  ```
  winget install --id GitHub.cli
  ```
- Verified install with:
  ```
  gh --version
  ```

## 4. Authenticate with GitHub
```
gh auth login
```
Prompts answered:
1. **Where do you use GitHub?** → `GitHub.com`
2. **Preferred protocol for Git operations?** → `HTTPS`
3. **Authenticate Git with your GitHub credentials?** → `Yes`
4. **How would you like to authenticate?** → `Login with a web browser`
5. Copied the one-time code shown in the terminal, browser opened automatically, pasted the code, and clicked **Authorize GitHub CLI**.
6. Confirmed success: `✓ Logged in as <username>`

## 5. Create Local Project Folder & Initialize Git
```
cd D:\Projects
mkdir nyc-collisions-data-engineering
cd nyc-collisions-data-engineering
git init
```

**Local project path:** `D:\Projects\nyc-collisions-data-engineering`

**Lesson learned:** Command Prompt does not handle multi-line pasted commands well — running `mkdir nyc-collisions-data-engineering cd nyc-collisions-data-engineering git init` as one pasted block caused `cd`, `git`, and `init` to be interpreted as extra folder names instead of separate commands. Fix: run commands **one at a time**, pressing Enter after each.

## 6. Create Project Folder Structure
```
mkdir dags
mkdir dbt
mkdir ingestion
mkdir docs
```

Resulting structure:
```
D:\Projects\nyc-collisions-data-engineering\
├── dags/          # Airflow DAGs
├── dbt/           # dbt Cloud project (models, tests, config)
├── ingestion/     # Python scripts for pulling data from Socrata API
├── docs/          # Documentation, diagrams
└── README.md
```

## Next Steps (to be added to this doc as completed)
- [ ] Add `.gitignore` (exclude secrets, `__pycache__`, dbt `target/`, Airflow logs, etc.)
- [ ] Add README.md to repo root
- [ ] First commit + push to GitHub
- [ ] Create the remote repo on GitHub (public: `nyc-collisions-data-engineering`) and link it as `origin`
