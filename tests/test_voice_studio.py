import base64
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from io import BytesIO
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import voice_studio


TEST_VOICES = [
    {
        "ShortName": "en-US-TestVoice",
        "FriendlyName": "Test Voice",
        "Locale": "en-US",
        "LocaleName": "English (United States)",
        "Gender": "Female",
    }
]


class TextExtractionTests(unittest.TestCase):
    def test_plain_text_strips_utf8_bom(self):
        self.assertEqual(
            voice_studio._extract_text("script.txt", b"\xef\xbb\xbfHello"),
            "Hello",
        )

    def test_html_extraction_omits_script_and_style(self):
        document = b"<p>Readable</p><script>secret()</script><style>.x{}</style>"
        self.assertEqual(voice_studio._extract_text("page.html", document), "Readable")

    def test_docx_extraction_reads_paragraphs(self):
        document = BytesIO()
        with ZipFile(document, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>First paragraph</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>",
            )

        self.assertEqual(
            voice_studio._extract_text("script.docx", document.getvalue()),
            "First paragraph\nSecond paragraph",
        )

    def test_pdf_extraction_reads_page_text(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font}
                )
            }
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 72 720 Td (PDF text) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
        document = BytesIO()
        writer.write(document)

        self.assertIn(
            "PDF text",
            voice_studio._extract_text("script.pdf", document.getvalue()),
        )

    def test_unsupported_extension_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "file type is not supported"):
            voice_studio._extract_text("script.doc", b"contents")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.offline_voices_patcher = patch(
            "voice_studio.get_windows_voices", return_value=TEST_VOICES
        )
        cls.online_voices_patcher = patch(
            "voice_studio.get_voices", return_value=TEST_VOICES
        )
        cls.offline_voices_patcher.start()
        cls.online_voices_patcher.start()
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), voice_studio.VoiceOverHandler
        )
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)
        cls.offline_voices_patcher.stop()
        cls.online_voices_patcher.stop()

    def send_json(self, path, payload):
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        return response.status, response.headers, response.read()

    def test_homepage_serves_the_app(self):
        with urlopen(f"{self.base_url}/", timeout=5) as response:
            page = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Voice Studio", page)
        self.assertIn('id="engine-select"', page)

    def test_voice_list_uses_offline_engine_by_default(self):
        with patch("voice_studio.get_windows_voices", return_value=TEST_VOICES):
            with urlopen(f"{self.base_url}/api/voices", timeout=5) as response:
                payload = json.load(response)
        self.assertEqual(payload["voices"], TEST_VOICES)

    def test_invalid_engine_is_rejected(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base_url}/api/voices?engine=invalid", timeout=5)
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(
            json.loads(error.exception.read())["error"],
            "Choose an available voice engine.",
        )
        error.exception.close()

    def test_offline_generation_returns_requested_audio_format(self):
        audio = b"RIFF" + b"\x00" * 48
        with patch("voice_studio._synthesize_windows", return_value=audio) as synthesize:
            status, headers, body = self.send_json(
                "/api/generate",
                {
                    "engine": "offline",
                    "voice": "en-US-TestVoice",
                    "text": "A test script.",
                    "rate": 0,
                    "pitch": 0,
                    "volume": 0,
                    "format": "wav",
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "audio/wav")
        self.assertEqual(body, audio)
        synthesize.assert_called_once_with(
            "A test script.", "en-US-TestVoice", 0, 0, "wav"
        )

    def test_online_generation_returns_mp3(self):
        audio = b"ID3" + b"\x00" * 48
        with patch(
            "voice_studio._synthesize", new=AsyncMock(return_value=audio)
        ) as synthesize:
            status, headers, body = self.send_json(
                "/api/generate",
                {
                    "engine": "edge",
                    "voice": "en-US-TestVoice",
                    "text": "An online test script.",
                    "rate": 0,
                    "pitch": 0,
                    "volume": 0,
                    "format": "mp3",
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "audio/mpeg")
        self.assertEqual(body, audio)
        synthesize.assert_awaited_once_with(
            "An online test script.",
            "en-US-TestVoice",
            0,
            0,
            0,
        )

    def test_scripts_above_fifty_thousand_characters_are_accepted(self):
        text = "A" * 50_001
        with patch("voice_studio._synthesize_windows", return_value=b"RIFF") as synthesize:
            status, _, _ = self.send_json(
                "/api/generate",
                {
                    "engine": "offline",
                    "voice": "en-US-TestVoice",
                    "text": text,
                    "format": "wav",
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(len(synthesize.call_args.args[0]), 50_001)

    def test_document_api_extracts_uploaded_text(self):
        status, headers, body = self.send_json(
            "/api/extract",
            {
                "filename": "script.txt",
                "content": base64.b64encode(b"Hello from a document").decode(),
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "application/json")
        self.assertEqual(json.loads(body)["text"], "Hello from a document")

    def test_invalid_voice_is_rejected(self):
        status, headers, body = self.send_json(
            "/api/generate",
            {
                "engine": "offline",
                "voice": "unknown",
                "text": "A test script.",
                "format": "mp3",
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(headers.get_content_type(), "application/json")
        self.assertIn("Choose a voice", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
