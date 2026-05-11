# Contributing

Thanks for taking a look at Scrolly Polly Notely.

## Local Setup

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

Some tests create Tkinter windows and work best in a normal desktop session.

## Pull Requests

- Keep changes small and focused.
- Include tests for behavior changes when practical.
- Do not commit personal note data, generated pasted images, caches, or local runtime config.
- Keep the app local-first: no telemetry or network behavior beyond the existing localhost helper socket.

## Data Safety

By default, user data lives outside the project folder:

```text
%APPDATA%\ScrollyPollyNotely
```

Use `SCROLLY_POLLY_NOTELY_DATA_DIR` when testing data-path changes.
