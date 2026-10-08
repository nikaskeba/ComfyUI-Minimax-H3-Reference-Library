import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock


class VoiceRouteTests(unittest.IsolatedAsyncioTestCase):
    def route(self, fields, files):
        tree = ast.parse((Path(__file__).parents[1] / "server.py").read_text(encoding="utf-8"))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "voice_description")
        function.decorator_list = []
        env = {"asyncio": asyncio, "_read_multipart": AsyncMock(return_value=(fields, files)),
               "describe_file": Mock(return_value={"description": "warm", "seconds": 3}),
               "get_record": Mock(return_value={"audio_file": "managed.wav"}),
               "media_path": Mock(return_value="managed/path.wav"),
               "_built_in_by_attachment_id": Mock(return_value={"name": "Example"}),
               "built_in_audio_filename": Mock(return_value="builtin.wav"),
               "web": SimpleNamespace(json_response=lambda value: value), "_error_response": lambda error: {"error": str(error)}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "server.py", "exec"), env)
        return env

    async def test_new_upload_precedes_saved_reference(self):
        env = self.route({"kind": "library", "id": "x"}, {"audio": ("voice.wav", b"voice")})
        result = await env["voice_description"](None)
        self.assertEqual(result["description"], "warm")
        env["describe_file"].assert_called_once_with(b"voice")
        env["get_record"].assert_not_called()

    async def test_saved_sources_use_managed_resolution(self):
        for kind in ("builtin", "library"):
            env = self.route({"kind": kind, "id": "record"}, {})
            await env["voice_description"](None)
            env["media_path"].assert_called_once()
            env["describe_file"].assert_called_once_with("managed/path.wav")

    async def test_paths_and_urls_are_not_accepted(self):
        env = self.route({"path": "C:/private.wav", "url": "https://example.com/audio.wav"}, {})
        result = await env["voice_description"](None)
        self.assertIn("error", result)
        env["describe_file"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
