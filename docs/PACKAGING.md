# Packaging

Scrolly Polly Notely can be packaged as a portable Windows folder with PyInstaller.

The build keeps user notes outside the app folder. Packaged builds still store data in:

```text
%APPDATA%\ScrollyPollyNotely
```

## Build A Portable App

From the repository root on Windows:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m PyInstaller scrolly-polly-notely.spec --clean --noconfirm
```

The portable app is created at:

```text
dist\ScrollyPollyNotely\ScrollyPollyNotely.exe
```

Zip the `dist\ScrollyPollyNotely` folder if you want to share a downloadable build.

## Verify Before Sharing

Run the test suite before packaging:

```powershell
python -m pytest -q
```

Then smoke test the packaged app:

1. Launch `dist\ScrollyPollyNotely\ScrollyPollyNotely.exe`.
2. Create a note from the hub.
3. Edit text, right-click inside edit mode, and paste text.
4. Toggle light mode, dark mode, and transparent background.
5. Restart the packaged app and confirm the note is restored.

## Clean Generated Files

Generated packaging output is ignored by Git:

```text
build\
dist\
```
