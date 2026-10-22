# Contributing

Thanks for helping improve Voice Studio. Changes should preserve the local-first design and keep the offline speech path independent of network services.

## Before opening a pull request

1. Open an issue for a substantial feature or behavior change so the scope can be agreed upon.
2. Keep changes focused and avoid adding a frontend build system or runtime dependency without a clear need.
3. Add or update tests for changed behavior. Unit and API tests must not make external network requests.
4. Update the README when setup, supported formats, privacy, or user-facing behavior changes.
5. Run the checks locally:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   node --check web\app.js
   ```

## Pull requests

Describe the user-visible change, explain how it was tested, and mention any setup or privacy impact. Do not include generated audio, virtual environments, credentials, or personal documents in a pull request.

## Reporting problems

Use the repository issue templates. Include the Windows version, Python version, selected speech engine, steps to reproduce, and the exact error message. Do not attach private scripts, personal documents, generated audio, or access tokens.
