# agy-switch (Gemini Switch)

A multi-account manager & switcher for Google Antigravity CLI (`agy`), Antigravity IDE, and Gemini.

This tool allows you to easily seamlessly switch between multiple Google accounts in Antigravity, without needing to re-login every time.

## 🌟 Features
- **Fast Switching**: Jump between Personal, Work, or Test accounts instantly.
- **Project accounts on WSL**: Use `switch` inside a project, then start `agy` normally. Different projects can run with different accounts at the same time.
- **Per-account Quotas**: See separate 5-hour and weekly remaining percentages and reset times for every account.
- **Credential storage**: Standard installs use the OS keyring. The WSL file adapter keeps credentials in owner-only files.
- **Cross-Platform**: Account management supports Linux, macOS, and Windows; project isolation currently supports the WSL file adapter.
- **Auto-migration**: If you were using an older version, it will automatically and securely migrate your plain-text tokens into the secure keyring.

## 🛠 Installation

You can install `agy-switch` directly using `pip`.

### From GitHub (Latest Version)
```bash
pip install git+https://github.com/atang-sp/agy-switch.git
```

### From Local Source
If you have cloned the repository, you can install it locally:
```bash
git clone https://github.com/atang-sp/agy-switch.git
cd agy-switch
pip install .
```

*Note: Once installed via `pip`, the `agy-switch` (and `gemini-switch`) commands will automatically be available in your terminal!*

## 📖 Usage

Run `agy-switch` without arguments to see the current active account and the list of available profiles.

### Commands

- **`agy-switch list` (or `ls`)**
  List saved account aliases and live quota information. The compact view shows only each account's email, 5-hour quota, weekly quota, and reset countdown.

- **`agy-switch current` (or `status`, `whoami`)**
  View the current account and its live quotas.

  Use `agy-switch list --no-quota` or `agy-switch current --no-quota` to skip network queries.

- **`agy-switch save [alias]`**
  Save the current active account as a profile (e.g., `agy-switch save work`).

- **`agy-switch alias [old_alias|email] <new_alias>` (or `rename`)**
  Set or rename an account alias. If only `<new_alias>` is provided, it updates the currently active account.

- **`agy-switch add [alias]`**
  Add a Google account. If your current active account is not yet aliased, it prompts you to save it directly. Otherwise, it triggers the browser login flow to add a new account.

- **`agy-switch switch [alias|email]` (or `use`)**
  On the WSL file credential setup, assign a saved account to the current Git
  project (or current directory outside Git). Use `--global` to switch the
  shared default account and `--default` to clear the current project binding.
  Global switching requires all running `agy` sessions to exit first.

- **`agy-switch remove [alias|email]` (or `rm`)**
  Delete a saved profile from the system.

### Different accounts for different projects (WSL file credential setup)

First save each account with `agy-switch add` or `agy-switch save`. Then run:

```bash
cd /path/to/work-project
agy-switch switch work
agy

cd /path/to/personal-project
agy-switch switch personal
agy
```

`switch` accepts a saved alias or email. It binds the Git worktree root, so
commands from its subdirectories use the same account. Outside Git, the current
directory is the project. `agy-switch current` shows the selected account.
Run `agy-switch switch --default` to clear a project binding.

The local shell integration gives each project/account pair its own `HOME` and
`~/.gemini/antigravity-cli/antigravity-oauth-token`. Other entries in your home
directory are linked into this isolated home so common tool configuration remains
available. The global active account is unchanged. If installing on another WSL
machine, add this function to `~/.bashrc` so `agy` reads the project binding:

```bash
agy() { agy-switch --launch-agy "$@"; }
```

For Fish, create `~/.config/fish/functions/agy.fish` with:

```fish
function agy
    agy-switch --launch-agy $argv
end
```

Check `type agy` in the shell where you launch it: it should show the function.
Restart any `agy` sessions that were opened before installing the function.

This project isolation currently supports the local WSL file credential adapter
described in [LOCAL_SETUP.md](LOCAL_SETUP.md). It does not change the account of
the Antigravity IDE or installations that use an OS keyring for active credentials.

Already-running sessions keep the account with which they started.

## 🔐 Security Note
Standard installations store tokens (including refresh tokens) in the OS keyring
under `gemini` and `gemini-accounts`. The WSL file credential adapter stores
them in owner-only files, including project credentials; see
[LOCAL_SETUP.md](LOCAL_SETUP.md). Account aliases, emails, and project bindings
are stored separately as metadata.

## Quota details

Quota queries use the `daily-cloudcode-pa.googleapis.com` host and Google's
`retrieveUserQuotaSummary` endpoint, matching the Antigravity CLI's account quota
path. The regular `cloudcode-pa.googleapis.com` host is deliberately not used as
a fallback because it can return an availability-style all-100 Gemini response.
If the daily endpoint fails, this tool reports the error instead of showing a
different host's potentially misleading result. Percentages mean **remaining**
quota, clearly labeled as remaining, separately for the
`5h` and `weekly` windows in each returned model group. Claude and GPT-OSS are
one shared pool, so the service does not expose a separate Claude-only meter.
Reset times are displayed in your local timezone with a countdown. Missing values
appear as unavailable, never as an assumed zero or 100%.

Expired consumer access tokens are refreshed temporarily for the query. Viewing
quotas does not switch accounts, modify saved credentials, or run model requests.
Requests have a 12-second timeout each, with up to four accounts queried
concurrently. A failure for one account leaves the others visible. This internal
Google endpoint may change; unsupported responses and network errors are shown
per account.
