# agy-switch (Gemini Switch)

A multi-account manager & switcher for Google Antigravity CLI (`agy`), Antigravity IDE, and Gemini.

This tool allows you to easily seamlessly switch between multiple Google accounts in Antigravity, without needing to re-login every time.

## 🌟 Features
- **Fast Switching**: Jump between Personal, Work, or Test accounts instantly.
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
  List all saved account profiles.

- **`agy-switch current` (or `status`, `whoami`)**
  View details of the currently active account.

- **`agy-switch save [alias]`**
  Save the current active account as a profile (e.g., `agy-switch save work`).

- **`agy-switch add [alias]`**
  Add a completely new Google account. It will open your browser to complete the login, and then securely save it.

- **`agy-switch switch [alias|email]` (or `use`)**
  Switch to a saved account. You can use the alias you provided or the email address.

- **`agy-switch remove [alias]` (or `rm`)**
  Delete a saved profile from the system.

## 🔐 Security Note
All tokens (including sensitive refresh tokens) are securely stored in your OS's native Keyring system under the service name `gemini` and `gemini-accounts`. Only non-sensitive metadata (aliases and emails) are stored in `~/.gemini/accounts_meta.json`.
