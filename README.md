# agy-switch (Gemini Switch)

A multi-account manager & switcher for Google Antigravity CLI (`agy`), Antigravity IDE, and Gemini.

This tool allows you to easily seamlessly switch between multiple Google accounts in Antigravity, without needing to re-login every time.

## 🌟 Features
- **Fast Switching**: Jump between Personal, Work, or Test accounts instantly.
- **Per-account Quotas**: See separate 5-hour and weekly remaining percentages and reset times for every account.
- **Secure**: Uses your operating system's native secure credential store (Linux Secret Service, macOS Keychain, Windows Credential Locker) via the `keyring` library. No tokens are stored in plain text.
- **Cross-Platform**: Works flawlessly on Linux, macOS, and Windows.
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
  Switch to a saved account. You can use the alias you provided or the email address.
  All running `agy` sessions must be exited first. An existing session keeps its
  startup account in memory and can overwrite the shared credential when its
  access token refreshes, so the switcher refuses unsafe live switching.

- **`agy-switch remove [alias|email]` (or `rm`)**
  Delete a saved profile from the system.

`agy-switch current` reports the credential that a newly started `agy` process
will use. Already-running sessions keep the account with which they started.

## 🔐 Security Note
All tokens (including sensitive refresh tokens) are securely stored in your OS's native Keyring system under the service name `gemini` and `gemini-accounts`. Only non-sensitive metadata (aliases and emails) are stored in `~/.gemini/accounts_meta.json`.

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
