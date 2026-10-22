# Voice Studio

A private-by-default Windows desktop companion for turning scripts and documents into speech. Choose built-in Windows voices for local, offline generation or switch to Microsoft Edge neural voices when online synthesis is available.

[![Checks](https://github.com/Shaayan-shah/voice-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Shaayan-shah/voice-studio/actions/workflows/ci.yml)

## Highlights

- **One interface, two speech engines.** Use installed Windows voices offline or optional Microsoft Edge neural voices online.
- **MP3 and WAV downloads.** Offline MP3 encoding runs locally. Online MP3 audio can be converted to WAV in the browser.
- **Work with documents.** Import PDF, DOCX, TXT, Markdown, CSV, TSV, LOG, HTML, RTF, JSON, and XML files, or type and paste your script.
- **Choose the delivery.** Filter voices by language and speaker, choose a delivery preset, and adjust speed, pitch, and volume where supported.
- **Preview before saving.** Listen in the browser and download the finished recording.
- **Local-first operation.** The app binds to your computer only. Offline speech and document extraction stay local.

## Requirements

- Windows 10 or newer with PowerShell and Windows speech components.
- Python 3.10 or newer available through the Windows Python Launcher (`py`).
- An internet connection for the initial dependency installation.
- For offline speech, at least one compatible voice installed in Windows. Voice choices depend on the installed Windows speech packs.

## Quick start

1. Download or clone this repository to your Windows PC.
2. Double-click **Run Voice Studio.bat**.
3. On first launch, the script creates a project-local `.venv` and installs the requirements. This downloads the optional online voice client, PDF reader, and local MP3 encoder.
4. Your browser opens Voice Studio. Keep the command window open while using the app. Press `Ctrl+C` in the command window to stop it.
5. Choose **Offline · Windows voices** to generate speech without an internet connection. Choose **Online · Neural voices** when you want Edge neural speakers.

The app uses a free local port and listens only on `127.0.0.1`; it is not a public web server. Generated audio is previewed in the browser and is not saved automatically. Select **Download** to choose where your recording is saved.

## Voice engines and formats

| Engine | Internet | Voice source | MP3 | WAV |
| --- | --- | --- | --- | --- |
| Offline | Not needed after setup | Voices installed in Windows | Local FFmpeg encoding | Native Windows speech output |
| Online | Required | Microsoft Edge TTS | Direct synthesis | Converted in your browser |

Offline synthesis has no provider account or per-generation service quota. Processing speed and practical script size depend on your computer's memory, available Windows voices, and the size of each request. Imported documents are limited to 20 MB; the local HTTP service rejects requests larger than 30 MB. Online synthesis depends on Microsoft's service availability and policies.

The Windows speech engine exposes speed and volume controls; pitch adjustment is available with online neural voices. Delivery presets adjust the supported speech settings.

## Importing documents

Drop a document into the upload area or browse for a file. The app extracts text locally from PDF, DOCX, TXT, Markdown, CSV, TSV, LOG, HTML, RTF, JSON, and XML. Plain text can also be dropped directly into the editor. Scanned PDFs need OCR before their contents can be extracted. Password-protected or damaged files may not import.

## Privacy

- Voice Studio serves the interface on the loopback address `127.0.0.1`; it does not expose an internet-facing server.
- Document text extraction happens on your computer.
- Offline synthesis and MP3 conversion happen on your computer.
- If you select the online engine, the script you submit is sent to Microsoft Edge TTS to synthesize speech. The online provider's privacy terms then apply.
- Audio is held temporarily for playback and download. Voice Studio does not create an audio library or upload recordings.

## Troubleshooting

### The first launch cannot install requirements

Check that Python 3.10 or newer and the `py` launcher are installed, and that the PC can access the Python package index. Run **Run Voice Studio.bat** again; it repairs an incomplete environment.

### No offline speakers appear

Install a Windows speech voice pack in Windows Settings and restart Voice Studio. Only voices enabled for the Windows speech API appear in the list.

### Online speakers do not load or generation times out

Check the internet connection and try again, or switch to **Offline · Windows voices**. The online engine depends on Microsoft's service and network availability.

### PDF text is missing

Scanned pages are images rather than selectable text. Run OCR on the PDF before importing it.

## Development

The UI uses plain HTML, CSS, and JavaScript without a frontend build step. The local Python server uses the Python standard library and the packages in `requirements.txt`.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web\app.js
```

The test suite uses mocked speech engines for API tests, so it does not contact Microsoft or require Windows voices. A real offline synthesis check can be run by starting the app and creating a short recording with the offline engine.

## Project layout

```text
.
|-- .github/
|   |-- ISSUE_TEMPLATE/
|   `-- workflows/ci.yml
|-- tests/
|-- web/
|   |-- app.js
|   |-- favicon.svg
|   |-- index.html
|   `-- styles.css
|-- Demo.py
|-- LICENSE
|-- README.md
|-- requirements.txt
`-- Run Voice Studio.bat
```

## GitHub Pages

Voice Studio requires a local Python process and Windows speech components, so it cannot be deployed as a working static GitHub Pages site. This repository contains the source and CI checks; hosting a shared online version would require a separate Python-capable service and deployment design.

## License

Voice Studio is released under the MIT License. See [LICENSE](./LICENSE).
