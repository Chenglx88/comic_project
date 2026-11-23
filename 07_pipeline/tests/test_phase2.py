"""Phase 2 离线测试：L4 归一化/校验与 Seedream 适配器。"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

import compose  # noqa: E402
import config as config_module  # noqa: E402
import l4  # noqa: E402
import media_image  # noqa: E402
import media_tts  # noqa: E402
import media_video  # noqa: E402

LOCK = {
    "protagonists": {
        "lie": {
            "prompt_prefix": "PREFIX, red hair",
            "seed_range": [100, 199],
        }
    }
}
DIGEST = "sha256:test"


def shot(shot_id: str, action: str = "试炼者观察阵盘") -> dict:
    return {
        "shot_id": shot_id,
        "beat": "1",
        "scene": "讲道台",
        "shot_size": "中景",
        "camera_move": "固定",
        "duration_sec": "4",
        "action": action,
    }


class L4Tests(unittest.TestCase):
    def test_normalize_s001_injects_lock_and_text2img(self):
        data = l4._normalize({}, shot("S001"), "lie", LOCK, DIGEST)
        self.assertIn("PREFIX, red hair", data["text2img"]["prompt"])
        self.assertTrue(100 <= data["seed"] <= 199)
        self.assertEqual(data["consistency"], {"method": "text2img", "reference_image": ""})
        self.assertIn("EP01_computer_S001_v2.png", data["img2video"]["first_frame"])
        self.assertEqual(data["img2video"]["params"]["duration_sec"], 4.0)
        self.assertEqual(l4.validate_prompt(data, shot("S001"), "lie", LOCK, DIGEST), [])

    def test_normalize_later_shot_uses_s001_reference(self):
        data = l4._normalize({}, shot("S002"), "lie", LOCK, DIGEST)
        self.assertEqual(data["consistency"]["method"], "img2img")
        self.assertEqual(data["consistency"]["reference_image"], l4.REFERENCE_S001)
        self.assertEqual(l4.validate_prompt(data, shot("S002"), "lie", LOCK, DIGEST), [])

    def test_validate_rejects_missing_prefix_and_bad_digest(self):
        data = l4._normalize({}, shot("S001"), "lie", LOCK, DIGEST)
        data["text2img"]["prompt"] = "没有角色锁前缀的画面"
        data["character_lock_digest"] = "sha256:wrong"
        errors = l4.validate_prompt(data, shot("S001"), "lie", LOCK, DIGEST)
        self.assertTrue(any("prompt_prefix" in error for error in errors))
        self.assertTrue(any("digest" in error for error in errors))

    def test_extract_prompts_accepts_object_and_array(self):
        self.assertEqual(len(l4._extract_prompts('{"prompts":[{"shot_id":"S001"}]}')), 1)
        self.assertEqual(len(l4._extract_prompts('[{"shot_id":"S001"}]')), 1)
        with self.assertRaises(ValueError):
            l4._extract_prompts('{"other":[]}')


class MediaImageTests(unittest.TestCase):
    def test_image_size_png(self):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1920, 1080)
        self.assertEqual(media_image._image_size(header + b"\x00" * 8), (1920, 1080))

    def test_build_payload_with_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.png"
            ref.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            payload = media_image._build_payload("model", "prompt", "negative", "1920x1080", ref)
        self.assertEqual(payload["model"], "model")
        self.assertEqual(payload["n"], 1)
        self.assertTrue(payload["image_urls"][0].startswith("data:image/png;base64,"))

    def test_generate_requires_ark_key(self):
        cfg = config_module.Config(values={"SEEDREAM_ENDPOINT_ID": "ep-test"})
        with self.assertRaises(media_image.MediaError):
            media_image.generate("prompt", "negative", 1, "/tmp/x.png", config_obj=cfg)

    def test_generate_requires_model(self):
        cfg = config_module.Config(values={"ARK_API_KEY": "set"})
        with self.assertRaises(media_image.MediaError):
            media_image.generate("prompt", "negative", 1, "/tmp/x.png", config_obj=cfg)


class MediaTtsTests(unittest.TestCase):
    def test_parse_audio_ndjson_and_sse(self):
        import base64

        first = base64.b64encode(b"abc").decode("ascii")
        second = base64.b64encode(b"def").decode("ascii")
        raw = (
            f'{{"code":0,"data":"{first}"}}\n'
            f'data: {{"code":0,"data":"{second}"}}\n'
        ).encode("utf-8")
        self.assertEqual(media_tts._parse_audio(raw), b"abcdef")

    def test_parse_audio_accepts_end_code_and_concatenated_json(self):
        import base64

        first = base64.b64encode(b"abc").decode("ascii")
        second = base64.b64encode(b"def").decode("ascii")
        raw = (
            f'{{"code":0,"data":"{first}"}}'
            f'{{"code":20000000,"message":"ok","data":"{second}"}}'
        ).encode("utf-8")
        self.assertEqual(media_tts._parse_audio(raw), b"abcdef")

    def test_parse_audio_rejects_error_code(self):
        with self.assertRaises(media_tts.MediaError):
            media_tts._parse_audio(b'{"code":45000030,"data":""}\n')

    def test_synth_requires_key(self):
        cfg = config_module.Config(values={"VOLC_TTS_CLUSTER": "seed-tts-2.0"})
        with self.assertRaises(media_tts.MediaError):
            media_tts.synth("台词", "voice", "/tmp/a.mp3", config_obj=cfg)


class MediaVideoTests(unittest.TestCase):
    def test_extract_task_accepts_object_and_list(self):
        self.assertEqual(media_video._extract_task({"data": {"id": "t1"}})["id"], "t1")
        self.assertEqual(media_video._extract_task({"data": [{"id": "t2"}]})["id"], "t2")

    def test_extract_video_url_new_and_classic_shapes(self):
        self.assertEqual(
            media_video._extract_video_url({"status": "succeeded", "url": "https://x/v.mp4"}),
            "https://x/v.mp4",
        )
        self.assertEqual(
            media_video._extract_video_url({"outputs": [{"url": "https://x/o.mp4"}]}),
            "https://x/o.mp4",
        )
        self.assertEqual(
            media_video._extract_video_url(
                {"task_result": {"videos": [{"id": "v1", "url": "https://x/c.mp4"}]}}
            ),
            "https://x/c.mp4",
        )
        self.assertEqual(media_video._extract_video_url({"status": "succeeded"}), "")

    def test_image_to_video_requires_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.png"
            first.write_bytes(b"\x89PNG\r\n\x1a\n")
            cfg = config_module.Config(values={})
            with self.assertRaises(media_video.MediaError):
                media_video.image_to_video(first, "prompt", 4, Path(tmp) / "out.mp4", config_obj=cfg)


class ComposeBgmTests(unittest.TestCase):
    """离线验证 BGM 铺轨与四路混音，不依赖网络。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audio = self.root / "audio"
        self.bgm_dir = self.audio / "bgm"
        self.bgm_dir.mkdir(parents=True)
        self.work = self.root / "work"
        self.work.mkdir()
        patcher = mock.patch.object(compose, "AUDIO_DIR", self.audio)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _tone(self, path: Path, seconds: float, freq: int = 440) -> Path:
        subprocess.run(
            [
                config_module.tool_path("ffmpeg"),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={freq}:sample_rate=48000:duration={seconds}",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(path),
            ],
            capture_output=True,
            check=True,
        )
        return path

    def test_build_bgm_returns_none_when_empty(self):
        self.assertIsNone(compose._build_bgm(3.0, self.work))

    def test_build_bgm_picks_first_non_hidden_by_name(self):
        for name in ("b.wav", ".hidden.wav", "a.wav"):
            self.bgm_dir.joinpath(name).write_bytes(b"\x00")
        with mock.patch.object(compose, "_run") as run:
            path = compose._build_bgm(3.0, self.work)
        cmd = run.call_args.args[0]
        self.assertEqual(path, self.work / "bgm.wav")
        self.assertIn(str(self.bgm_dir / "a.wav"), cmd)
        self.assertEqual(cmd[cmd.index("-stream_loop") + 1], "-1")
        self.assertIn("volume=0.12,afade=t=in:st=0:d=1.5,afade=t=out:st=0.000:d=3", cmd)

    def test_build_bgm_loops_and_is_audible(self):
        self._tone(self.bgm_dir / "short.wav", 1.0)
        bgm = compose._build_bgm(3.0, self.work)
        self.assertIsNotNone(bgm)
        data = compose._probe(bgm)
        duration = float(data["format"]["duration"])
        self.assertAlmostEqual(duration, 3.0, delta=0.15)
        proc = subprocess.run(
            [
                config_module.tool_path("ffmpeg"),
                "-i",
                str(bgm),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        line = next(
            (ln for ln in proc.stderr.splitlines() if "mean_volume" in ln), ""
        )
        self.assertTrue(line, proc.stderr[-400:])
        self.assertGreater(float(line.split("mean_volume:")[1].split()[0]), -60.0)

    def test_mux_without_bgm_keeps_one_audio_stream(self):
        out = self._mux(None)
        streams = compose._probe(out)["streams"]
        self.assertEqual(sum(s["codec_type"] == "video" for s in streams), 1)
        self.assertEqual(sum(s["codec_type"] == "audio" for s in streams), 1)

    def test_mux_with_bgm_mixes_into_one_audio_stream(self):
        out = self._mux(self._tone(self.work / "bgm.wav", 1.0, freq=220))
        streams = compose._probe(out)["streams"]
        self.assertEqual(sum(s["codec_type"] == "video" for s in streams), 1)
        self.assertEqual(sum(s["codec_type"] == "audio" for s in streams), 1)
        audio = next(s for s in streams if s["codec_type"] == "audio")
        self.assertEqual(int(audio["sample_rate"]), 48000)
        self.assertEqual(int(audio["channels"]), 2)

    def _mux(self, bgm: Path | None) -> Path:
        video = self.work / "video.mp4"
        subprocess.run(
            [
                config_module.tool_path("ffmpeg"),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x240:rate=30:duration=3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(video),
            ],
            capture_output=True,
            check=True,
        )
        voice = self._tone(self.work / "voice.wav", 3.0, freq=880)
        srt = self.work / "sub.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试字幕\n", encoding="utf-8")
        out = self.work / "final.mp4"
        compose._mux(video, voice, srt, bgm, 3.0, out)
        return out


if __name__ == "__main__":
    unittest.main()
