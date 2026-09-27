# Changelog

## v0.2.0 - 2026-09-27

- Bind saved accounts to Git projects, with isolated CLI credentials so projects can use different accounts at the same time on the WSL file credential setup.
- Show each account's bound projects and running `agy` sessions alongside its quota in `agy-switch list`.
- Show separate Gemini and Claude/GPT-OSS quota windows and reset times for each saved account.
- Improve account aliases and new account setup, and prevent global credential switches while an `agy` session could overwrite them.
- Fix Python package contents and add tests for account, quota, and project behavior.

Project isolation applies to the WSL file credential adapter and the `agy` CLI. Restart existing `agy` sessions to use a newly selected project account.
