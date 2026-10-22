import asyncio
import base64
from importlib import import_module
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import webbrowser
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

try:
    import edge_tts
except ModuleNotFoundError:
    edge_tts = None


APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
MAX_REQUEST_BYTES = 30 * 1024 * 1024
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_voices = None
_voices_lock = threading.Lock()
POWERSHELL = "powershell.exe"

WINDOWS_VOICES_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = @(
        $synth.GetInstalledVoices() |
            Where-Object { $_.Enabled } |
            ForEach-Object {
                [pscustomobject]@{
                    ShortName = $_.VoiceInfo.Name
                    FriendlyName = $_.VoiceInfo.Name
                    Locale = $_.VoiceInfo.Culture.Name
                    LocaleName = $_.VoiceInfo.Culture.DisplayName
                    Gender = $_.VoiceInfo.Gender.ToString()
                }
            }
    )
    ConvertTo-Json -InputObject $voices -Compress
} finally {
    $synth.Dispose()
}
"""

WINDOWS_SYNTHESIS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String([Console]::In.ReadToEnd())
)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.SelectVoice($env:VOICE_STUDIO_VOICE)
    $synth.Rate = [int]$env:VOICE_STUDIO_RATE
    $synth.Volume = [int]$env:VOICE_STUDIO_VOLUME
    $synth.SetOutputToWaveFile($env:VOICE_STUDIO_OUTPUT)
    $synth.Speak($text)
} finally {
    $synth.Dispose()
}
"""


async def _list_voices():
    if edge_tts is None:
        raise RuntimeError(
            "Online voices are not installed. Connect to the internet and run Run Voice Studio.bat."
        )
    return await edge_tts.list_voices()


def get_voices():
    global _voices
    with _voices_lock:
        if _voices is None:
            _voices = asyncio.run(_list_voices())
        return _voices


def _run_powershell(script, *, input_text=None, environment=None, timeout=30):
    if os.name != "nt":
        raise RuntimeError("Offline Windows voices are only available on Windows.")
    command = [
        POWERSHELL,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or "The Windows speech service returned an error.")
    return result.stdout.strip()


def get_windows_voices():
    output = _run_powershell(WINDOWS_VOICES_SCRIPT)
    if not output:
        return []
    voices = json.loads(output)
    return voices if isinstance(voices, list) else [voices]


async def _synthesize(text, voice, rate, pitch, volume):
    if edge_tts is None:
        raise RuntimeError(
            "Online voices are not installed. Connect to the internet and run Run Voice Studio.bat."
        )
    communicator = edge_tts.Communicate(
        text,
        voice,
        rate=f"{rate:+d}%",
        pitch=f"{pitch:+d}Hz",
        volume=f"{volume:+d}%",
    )
    audio_chunks = []
    async for message in communicator.stream():
        if message["type"] == "audio":
            audio_chunks.append(message["data"])
    if not audio_chunks:
        raise RuntimeError("The voice service returned no audio.")
    return b"".join(audio_chunks)


def _synthesize_windows(text, voice, rate, volume, output_format):
    with tempfile.TemporaryDirectory(prefix="voice-studio-") as temp_dir:
        wav_path = Path(temp_dir) / "voice.wav"
        environment = os.environ.copy()
        environment.update(
            {
                "VOICE_STUDIO_VOICE": voice,
                "VOICE_STUDIO_RATE": str(max(-10, min(10, round(rate / 3)))),
                "VOICE_STUDIO_VOLUME": str(max(0, min(100, 100 + volume))),
                "VOICE_STUDIO_OUTPUT": str(wav_path),
            }
        )
        encoded_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
        _run_powershell(
            WINDOWS_SYNTHESIS_SCRIPT,
            input_text=encoded_text,
            environment=environment,
            timeout=None,
        )
        output_path = wav_path
        if output_format == "mp3":
            try:
                imageio_ffmpeg = import_module("imageio_ffmpeg")
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "Offline MP3 support is not installed. Run Run Voice Studio.bat while connected to install it."
                ) from error
            output_path = Path(temp_dir) / "voice.mp3"
            result = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(wav_path),
                    "-vn",
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=None,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                detail = result.stderr.strip() or "The MP3 encoder returned an error."
                raise RuntimeError(f"Could not encode offline MP3 audio. {detail}")
        audio = output_path.read_bytes()
        if not audio:
            raise RuntimeError("Windows speech synthesis returned an empty audio file.")
        return audio


def _text_from_docx(content):
    with zipfile.ZipFile(BytesIO(content)) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in document.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(
            node.text or ""
            for node in paragraph.iter(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
            )
        )
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _extract_text(filename, content):
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".tsv", ".log", ".json", ".xml", ".html", ".htm", ".rtf"}:
        text = content.decode("utf-8-sig", errors="replace")
        if suffix in {".html", ".htm"}:
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.parts = []
                    self.hidden_depth = 0

                def handle_starttag(self, tag, _attrs):
                    if tag in {"script", "style"}:
                        self.hidden_depth += 1

                def handle_endtag(self, tag):
                    if tag in {"script", "style"} and self.hidden_depth:
                        self.hidden_depth -= 1

                def handle_data(self, data):
                    if not self.hidden_depth:
                        self.parts.append(data)

            parser = TextExtractor()
            parser.feed(text)
            text = "\n".join(part.strip() for part in parser.parts if part.strip())
        elif suffix == ".rtf":
            text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
            text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
            text = re.sub(r"[{}]", " ", text)
        return text
    if suffix == ".docx":
        return _text_from_docx(content)
    if suffix == ".pdf":
        try:
            PdfReader = import_module("pypdf").PdfReader
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "PDF support is not installed. Run: python -m pip install -r requirements.txt"
            ) from error
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(
        "This file type is not supported. Use PDF, DOCX, TXT, Markdown, CSV, TSV, HTML, RTF, JSON, XML, or LOG."
    )


class VoiceOverHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format_string, *args):
        logging.info("%s - %s", self.address_string(), format_string % args)

    def _json_response(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise ValueError("The request is empty or larger than the 30 MB limit.")
        request = json.loads(self.rfile.read(length))
        if not isinstance(request, dict):
            raise ValueError("The request must contain a JSON object.")
        return request

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/voices":
            engine = parse_qs(urlparse(self.path).query).get(
                "engine", ["offline"]
            )[0]
            if engine == "offline":
                try:
                    self._json_response(200, {"voices": get_windows_voices()})
                except Exception as error:
                    logging.exception("Could not load offline voices")
                    self._json_response(
                        502, {"error": f"Could not load Windows speech voices. {error}"}
                    )
                return
            if engine != "edge":
                self._json_response(400, {"error": "Choose an available voice engine."})
                return
            try:
                self._json_response(200, {"voices": get_voices()})
            except Exception as error:
                logging.exception("Could not load voices")
                self._json_response(
                    502,
                    {"error": f"Could not load the voice list. Check your internet connection. {error}"},
                )
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        request = {}
        try:
            request = self._read_json()
            if path == "/api/extract":
                filename = Path(unquote(str(request.get("filename", "")))).name
                encoded = request.get("content", "")
                content = base64.b64decode(encoded, validate=True)
                if not filename or not content or len(content) > MAX_DOCUMENT_BYTES:
                    raise ValueError("Choose a non-empty file smaller than 20 MB.")
                text = _extract_text(filename, content)
                if not text.strip():
                    raise ValueError("No readable text was found in this file.")
                self._json_response(200, {"text": text, "filename": filename})
                return
            if path == "/api/generate":
                text = request.get("text")
                voice_id = request.get("voice")
                engine = request.get("engine", "offline")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Enter or import some text first.")
                if engine == "offline":
                    voices = get_windows_voices()
                elif engine == "edge":
                    voices = get_voices()
                else:
                    raise ValueError("Choose an available voice engine.")
                if voice_id not in {voice["ShortName"] for voice in voices}:
                    raise ValueError("Choose a voice from the speaker list.")
                rate = int(request.get("rate", 0))
                pitch = int(request.get("pitch", 0))
                volume = int(request.get("volume", 0))
                output_format = request.get("format", "mp3")
                if output_format not in {"mp3", "wav"}:
                    raise ValueError("Choose MP3 or WAV as the download format.")
                if not -30 <= rate <= 30 or not -25 <= pitch <= 25 or not -20 <= volume <= 20:
                    raise ValueError("One or more speech settings are outside the supported range.")
                if engine == "offline":
                    audio = _synthesize_windows(
                        text, voice_id, rate, volume, output_format
                    )
                    content_type = (
                        "audio/mpeg" if output_format == "mp3" else "audio/wav"
                    )
                else:
                    audio = asyncio.run(
                        _synthesize(text, voice_id, rate, pitch, volume)
                    )
                    content_type = "audio/mpeg"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(audio)
                return
            self._json_response(404, {"error": "Not found."})
        except (ValueError, json.JSONDecodeError) as error:
            self._json_response(400, {"error": str(error)})
        except Exception as error:
            logging.exception("Request failed")
            engine = request.get("engine", "offline")
            if path == "/api/generate" and engine == "offline":
                message = f"Offline audio generation failed. Check Windows voices and the MP3 encoder. {error}"
            elif path == "/api/generate":
                message = f"Online audio generation failed. Check the internet connection and try again. {error}"
            else:
                message = f"Could not complete the request. {error}"
            self._json_response(
                502, {"error": message}
            )


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", 0), VoiceOverHandler)
    address, port = server.server_address
    url = f"http://{address}:{port}"
    print(f"Voice Studio is running at {url}")
    print("Keep this window open while using the app. Press Ctrl+C to stop.")
    threading.Timer(1, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nVoice Studio stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
