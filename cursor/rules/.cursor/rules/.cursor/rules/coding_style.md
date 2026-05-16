Moon River Weather coding rules

- This project runs on macOS first, not Linux first.
- Prefer launchd over cron for scheduled jobs on weather-core.
- Always preserve the active Python interpreter through subprocess chains by using sys.executable.
- Prefer absolute paths for scheduled/background execution.
- Keep radar pipeline steps explicit and easy to debug.
- Never assume interactive shell environment variables exist.
- Log important pipeline stages clearly.
- Avoid changes that break KCLX or KJAX loop compatibility.
- Prefer minimal, surgical edits over broad refactors.
- When proposing changes, explain exactly which file and function will change.