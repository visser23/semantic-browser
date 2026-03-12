# Running Semantic Browser with Real Logged-In Profiles

Use persistent profiles when your agent needs continuity across sessions:

- durable authentication tokens
- SSO continuity
- cookie and localStorage persistence
- extension and trust-signal continuity

## Profile Modes

- `persistent`: launch directly against a real profile directory.
- `clone`: copy a profile into a temporary sandbox, then launch there.
- `ephemeral`: disposable browser context (stateless baseline).

## Python API

```python
session = await ManagedSession.launch(
    headful=False,
    profile_mode="persistent",
    profile_dir="/path/to/chrome-profile",
)
```

## CLI

```bash
semantic-browser launch --headless --profile-mode persistent --profile-dir "/path/to/chrome-profile"
```

## Service API

`POST /sessions/launch` request body:

```json
{
  "headful": false,
  "profile_mode": "persistent",
  "profile_dir": "/path/to/chrome-profile"
}
```

## Safety Guarantees

- Runtime never deletes profile directories.
- `close()` is non-destructive in attached modes.
- Attached CDP sessions assume browser/profile lifecycle is externally owned.
- `force_close_browser()` exists for explicit destructive control.

## Important Limits

- `storage_state_path` is a lightweight bootstrap and does not replicate full profile behavior.
- Some anti-bot and enterprise auth flows still require manual intervention.
