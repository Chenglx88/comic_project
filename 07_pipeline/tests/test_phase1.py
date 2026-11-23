"""Phase 1 离线测试：不触网、不读真实 .env、不调用媒体 API。"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

PIPELINE = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE.parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import config  # noqa: E402
import errors  # noqa: E402
import jsonutil  # noqa: E402
import l1  # noqa: E402
import l2  # noqa: E402
import l3  # noqa: E402
import llm  # noqa: E402
import preflight  # noqa: E402
from unittest import mock  # noqa: E402


def write_env(tmp: Path, body: str) -> Path:
    path = tmp / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def l1_payload() -> dict:
    return {
        "version": 2,
        "major": "计算机科学与技术",
        "major_en": "computer",
        "realm": "修仙境",
        "retrieved_at": "2026-11-22",
        "courses": [
            {
                "name": f"课程{i}",
                "explain": "解释",
                "learning_content": ["知识点一", "知识点二", "知识点三"],
                "labs_projects": ["实验一"],
                "abilities": ["能力一"],
                "source_url": f"https://example.com/c{i}",
                "year": 2026,
            }
            for i in range(1, 6)
        ],
        "employment": {
            "directions": [
                {
                    "name": f"方向{i}",
                    "explain": "解释",
                    "main_tasks": ["任务一", "任务二", "任务三"],
                    "employers": ["公司甲", "公司乙", "公司丙"],
                    "salary_range": "约 15-25K/月",
                    "abilities": ["能力一", "能力二"],
                    "source_url": f"https://example.com/d{i}",
                    "year": 2026,
                }
                for i in range(1, 6)
            ],
            "source_url": "https://example.com/jobs",
            "year": 2026,
        },
        "sources": [
            {"url": "https://example.com/a", "retrieved_at": "2026-11-22", "year": 2026}
        ],
    }


def l2_payload() -> dict:
    beats = []
    for i, name, start, end in (
        (1, "开场", 0, 18),
        (2, "课程", 18, 118),
        (3, "就业", 118, 198),
        (4, "收束", 198, 210),
    ):
        beats.append(
            {
                "index": i,
                "name": name,
                "start_sec": start,
                "end_sec": end,
                "summary": f"{name}段落内容",
            }
        )
    return {
        "version": 2,
        "episode_id": "EP01",
        "major": "计算机科学与技术",
        "major_en": "computer",
        "realm": "修仙境",
        "protagonist": "undecided",
        "logline": "试炼者闯入修仙境，用专业规则破局。",
        "beats": beats,
        "knowledge_points": [
            {
                "id": f"K{i}",
                "title": f"知识点{i}",
                "explain": "白话解释",
                "misconception": "常见误区",
                "source_ref": "S1",
            }
            for i in range(1, 4)
        ],
        "characters": ["试炼者", "守阵石灵"],
        "coverage": {
            "courses": [
                "数据结构与算法",
                "计算机组成原理",
                "操作系统",
                "计算机网络",
                "编译原理",
            ],
            "employment": [
                "计算机软硬件系统设计与开发",
                "应用软件开发与项目管理",
                "网络安全运维与信息安全",
                "人工智能与智能系统应用开发",
                "科研院所与高校的科学研究、教学",
            ],
        },
        "next_episode_hook": "下一境的规则开始松动。",
        "continuity": {"prev_summary": "首集，无上集", "open_threads": ["主殿的钟声"]},
        "sources": [
            {"url": "https://example.com/src", "retrieved_at": "2026-11-22", "year": 2026}
        ],
    }


def l3_payload(shot_count: int = 40, duration: float = 5.25) -> dict:
    shots = []
    for i in range(1, shot_count + 1):
        shots.append(
            {
                "shot_id": f"S{i:03d}",
                "beat": ((i - 1) % 4) + 1,
                "scene": "训练场",
                "shot_size": "中景",
                "camera_move": "固定",
                "duration_sec": duration,
                "action": "试炼者观察规则",
                "dialogue_id": "D001" if i == 1 else "",
                "prompt_file": f"S{i:03d}.json",
                "reference_shot": "S001" if i > 1 else "",
            }
        )
    return {
        "shots": shots,
        "dialogue": [
            {
                "dialogue_id": "D001",
                "character": "试炼者",
                "text": "先看规则。",
                "emotion": "冷静",
                "duration_sec": 3,
            }
        ],
        "foley": [
            {
                "cue_id": "F001",
                "shot_id": "S001",
                "type": "环境",
                "description": "风声",
                "timing": "0-3s",
            }
        ],
        "overlays": [
            {
                "overlay_id": f"O{index:03d}",
                "start_sec": (index - 1) * 20,
                "end_sec": index * 20,
                "kind": "course" if index <= 5 else "employment",
                "title": f"信息{index}",
                "body": f"内容{index}",
            }
            for index in range(1, 11)
        ],
    }


class EnvConfigTests(unittest.TestCase):
    def test_parse_env_and_redacted_snapshot_never_leaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_env(
                Path(tmp),
                "# comment\n"
                "export API_KEY='super-secret'\n"
                "QUOTED=\"quoted-value\"\n"
                "PLAIN=plain-value\n"
                "EMPTY=\n",
            )
            cfg = config.Config.from_files([path])
            self.assertEqual(cfg.get("API_KEY"), "super-secret")
            self.assertEqual(cfg.get("QUOTED"), "quoted-value")
            self.assertTrue(cfg.present("PLAIN"))
            self.assertFalse(cfg.present("EMPTY"))
            snap = cfg.redacted_snapshot(["API_KEY", "NOPE", "EMPTY"])
            self.assertEqual(snap, {"API_KEY": "<set>", "NOPE": "<missing>", "EMPTY": "<missing>"})
            blob = json.dumps(snap)
            for secret in ("super-secret", "quoted-value", "plain-value"):
                self.assertNotIn(secret, blob)
            with self.assertRaises(config.ConfigError) as ctx:
                cfg.require(["NOPE"])
            self.assertIn("NOPE", str(ctx.exception))
            self.assertNotIn("super-secret", str(ctx.exception))

    def test_routing_fallback_and_env_model(self):
        routing = config.load_routing()
        self.assertEqual(routing["fallback"], "none")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_env(Path(tmp), "QWEN_MODEL_ID=qwen-test-2026\n")
            cfg = config.Config.from_files([path])
            resolved = llm.resolve_layer("L2", cfg)
            self.assertEqual(resolved["model"], "qwen-test-2026")
            self.assertEqual(resolved["api_key"], "<missing>")


class ExtractJsonTests(unittest.TestCase):
    def test_plain_fenced_prose_and_bad(self):
        self.assertEqual(jsonutil.extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(
            jsonutil.extract_json('```json\n{"a": 2}\n```'), {"a": 2}
        )
        self.assertEqual(
            jsonutil.extract_json('说明文字\n{"a": {"b": 3}}\n结束'), {"a": {"b": 3}}
        )
        self.assertEqual(jsonutil.extract_json("[1, 2, 3]"), [1, 2, 3])
        with self.assertRaises(ValueError) as ctx:
            jsonutil.extract_json("这不是 JSON")
        self.assertIn("这不是 JSON", str(ctx.exception))


class L1ValidationTests(unittest.TestCase):
    def test_valid_payload(self):
        self.assertEqual(l1.validate_l1(l1_payload(), "computer"), [])

    def test_missing_course_year_and_bad_url(self):
        data = l1_payload()
        del data["courses"][0]["year"]
        data["courses"][1]["source_url"] = "ftp://example.com/x"
        errors = l1.validate_l1(data, "computer")
        self.assertTrue(any("year" in e for e in errors))
        self.assertTrue(any("http" in e for e in errors))

    def test_wrong_counts(self):
        data = l1_payload()
        data["courses"] = data["courses"][:4]
        data["employment"]["directions"] = data["employment"]["directions"][:4]
        errors = l1.validate_l1(data, "computer")
        self.assertTrue(any("courses" in e for e in errors))
        self.assertTrue(any("directions" in e for e in errors))

    def test_direction_source_retrieved_at_and_realm(self):
        data = l1_payload()
        del data["employment"]["directions"][0]["year"]
        data["retrieved_at"] = "2026/11/22"
        data["realm"] = "机枢城"
        errors = l1.validate_l1(data, "computer")
        self.assertTrue(any("directions[0].year" in e for e in errors))
        self.assertTrue(any("retrieved_at" in e for e in errors))
        self.assertTrue(any("realm" in e for e in errors))

    def test_course_and_employment_detail_required(self):
        data = l1_payload()
        data["courses"][0]["learning_content"] = ["只有一条"]
        data["employment"]["directions"][0]["employers"] = ["只有一家"]
        data["employment"]["directions"][0]["salary_range"] = ""
        errors = l1.validate_l1(data, "computer")
        self.assertTrue(any("learning_content" in e for e in errors))
        self.assertTrue(any("employers" in e for e in errors))
        self.assertTrue(any("salary_range" in e for e in errors))

    def test_forbidden_source_and_no_mentors(self):
        data = l1_payload()
        data["courses"][0]["source_url"] = "https://www.zhaosheng.com/437599.html"
        data["sources"][0]["retrieved_at"] = "2026/11/22"
        data["mentors"] = []
        errors = l1.validate_l1(data, "computer")
        self.assertTrue(any("聚合站" in e for e in errors))
        self.assertTrue(any("mentors" in e for e in errors))
        self.assertTrue(any("retrieved_at" in e for e in errors))

    def test_no_homepage_source(self):
        data = l1_payload()
        data["employment"]["directions"][0]["source_url"] = "https://xz.chsi.com.cn/"
        errors = l1.validate_l1(data, "computer")
        self.assertTrue(any("首页" in e for e in errors))


class L2ValidationTests(unittest.TestCase):
    def test_valid_payload(self):
        self.assertEqual(l2.validate_l2(l2_payload(), "EP01", "computer"), [])

    def test_v2_rejects_beat_timeline_drift(self):
        data = l2_payload()
        data["beats"][1]["end_sec"] = 85
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("时轴" in e for e in errors))

    def test_duration_out_of_range(self):
        data = l2_payload()
        data["beats"][-1]["end_sec"] = 250
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("时长" in e for e in errors))

    def test_forbidden_protagonist_and_bad_source(self):
        data = l2_payload()
        data["logline"] += "烈冲了出去。"
        data["sources"][0]["url"] = ""
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("烈" in e for e in errors))
        self.assertTrue(any("sources" in e for e in errors))

    def test_v2_requires_coverage(self):
        data = l2_payload()
        del data["coverage"]
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("coverage" in e for e in errors))

        data = l2_payload()
        data["coverage"]["courses"] = data["coverage"]["courses"][:4]
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("courses" in e for e in errors))

    def test_v2_coverage_must_match_l1(self):
        data = l2_payload()
        data["coverage"]["employment"][0] = "不存在的就业方向"
        errors = l2.validate_l2(
            data,
            "EP01",
            "computer",
            expected_coverage_data=l2.expected_coverage(),
        )
        self.assertTrue(any("coverage" in e for e in errors))

    def test_v2_rejects_mentor_content(self):
        data = l2_payload()
        data["mentors"] = [{"name": "某导师"}]
        data["mentor_portrait"] = {"note": "综合画像"}
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("导师" in e for e in errors))

    def test_ep01_prev_summary_must_not_invent_previous(self):
        data = l2_payload()
        data["continuity"]["prev_summary"] = "上集结尾，试炼者被卷入虚空。"
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("首集" in e or "无上集" in e for e in errors))

    def test_next_hook_must_not_jump_realm(self):
        data = l2_payload()
        data["next_episode_hook"] = "下一站指向机枢城。"
        errors = l2.validate_l2(data, "EP01", "computer")
        self.assertTrue(any("其它境" in e and "机枢城" in e for e in errors))

class L3ValidationTests(unittest.TestCase):
    def test_valid_payload(self):
        self.assertEqual(l3.validate_storyboard(l3_payload()), [])

    def test_coverage_requires_course_in_dialogue_and_job_in_overlay(self):
        data = l3_payload()
        script = {"coverage": {"courses": ["数据结构与算法"], "employment": ["网络安全"]}}
        errors = l3.validate_storyboard(data, script)
        self.assertTrue(any("课程名" in error for error in errors))
        self.assertTrue(any("就业方向" in error for error in errors))

    def test_coverage_requires_course_explain_and_foundation(self):
        data = l3_payload()
        data["dialogue"][0]["text"] = "数据结构与算法。"
        script = {"coverage": {"courses": ["数据结构与算法"], "employment": []}}
        errors = l3.validate_storyboard(data, script)
        self.assertTrue(any("主要学习内容" in error for error in errors))
        self.assertTrue(any("学习基础" in error for error in errors))

        data["dialogue"][0]["text"] = "数据结构与算法主要学研究数据怎么组织，需要编程基础。"
        self.assertEqual(l3.validate_storyboard(data, script), [])

    def test_overlay_kind_counts(self):
        data = l3_payload()
        data["overlays"] = data["overlays"][:9]
        errors = l3.validate_storyboard(data)
        self.assertTrue(any("employment 信息卡数量" in error for error in errors))

    def test_shot_count_and_duration_bounds(self):
        errors = l3.validate_storyboard(l3_payload(shot_count=39))
        self.assertTrue(any("镜头数" in e for e in errors))
        data = l3_payload(shot_count=40)
        data["shots"][0]["duration_sec"] = 9
        self.assertTrue(any("时长" in e for e in l3.validate_storyboard(data)))

    def test_duplicate_and_future_reference(self):
        data = l3_payload()
        data["shots"][1]["shot_id"] = "S001"
        data["shots"][0]["reference_shot"] = "S002"
        errors = l3.validate_storyboard(data)
        self.assertTrue(any("重复" in e for e in errors))
        self.assertTrue(any("未来" in e for e in errors))

    def test_unknown_dialogue_and_foley_shot(self):
        data = l3_payload()
        data["shots"][0]["dialogue_id"] = "D999"
        data["foley"][0]["shot_id"] = "S999"
        errors = l3.validate_storyboard(data)
        self.assertTrue(any("D999" in e for e in errors))
        self.assertTrue(any("S999" in e for e in errors))

    def test_self_reference_and_empty_foley_shot(self):
        data = l3_payload()
        data["shots"][0]["reference_shot"] = "S001"
        data["foley"][0]["shot_id"] = ""
        errors = l3.validate_storyboard(data)
        self.assertTrue(any("未来" in e for e in errors))
        self.assertTrue(any("shot_id 不存在" in e for e in errors))


class CsvTests(unittest.TestCase):
    def test_headers_and_row_counts(self):
        headers = json.loads(
            (PROJECT_ROOT / "00_schema" / "storyboard_headers.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmp:
            paths = l3.write_tables(l3_payload(), Path(tmp), headers)
            for name, expected_header in (
                ("shots", headers["shots"]),
                ("dialogue", headers["dialogue"]),
                ("foley", headers["foley"]),
            ):
                with paths[name].open(encoding="utf-8", newline="") as fh:
                    rows = list(csv.reader(fh))
                self.assertEqual(rows[0], expected_header)
                self.assertEqual(len(rows) - 1, len(l3_payload()[name]))


class ResumeGateTests(unittest.TestCase):
    def test_l1_resume_validator_failure_exits_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structured = root / "computer.json"
            structured.write_text(json.dumps(l1_payload(), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(
                l1, "_outputs", return_value=(structured, root / "raw")
            ), mock.patch.object(l1, "_run_validator", return_value=(False, "L1 invalid")):
                with self.assertRaises(errors.PipelineError) as ctx:
                    l1.run(resume=True)
        self.assertEqual(ctx.exception.code, 5)

    def test_l2_resume_validator_failure_exits_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "EP01_computer.json"
            output.write_text(json.dumps(l2_payload(), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(l2, "OUTPUT_DIR", root), mock.patch.object(
                l2, "_run_validator", return_value=(False, "episode invalid")
            ):
                with self.assertRaises(errors.PipelineError) as ctx:
                    l2.run(resume=True)
        self.assertEqual(ctx.exception.code, 5)

    def test_l3_resume_validator_failure_exits_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("shots", "dialogue", "foley", "overlays"):
                (root / f"{name}.csv").write_text("", encoding="utf-8")
            with mock.patch.object(l3, "OUTPUT_DIR", root), mock.patch.object(
                l3, "_run_validator", return_value=(False, "storyboard invalid")
            ):
                with self.assertRaises(errors.PipelineError) as ctx:
                    l3.run(resume=True)
        self.assertEqual(ctx.exception.code, 5)


class LlmClientTests(unittest.TestCase):
    def _cfg(self, tmp: Path):
        return config.Config.from_files(
            [write_env(tmp, "TOKENHUB_API_KEY=test-key\nHUNYUAN_MODEL_ID=hy4-test\n")]
        )

    def test_chat_requests_expected_payload_without_network(self):
        calls = []

        def fake_transport(request: Request, timeout: float):
            calls.append((request, timeout))
            body = {
                "choices": [
                    {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}
                ],
                "usage": {"total_tokens": 12},
                "model": "hy4-test",
            }
            return 200, json.dumps(body).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(Path(tmp))
            result = llm.chat(
                "L1",
                [{"role": "user", "content": "hi"}],
                config=cfg,
                transport=fake_transport,
                run_log=False,
            )
        self.assertEqual(result["content"], '{"ok": true}')
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["usage"], {"total_tokens": 12})
        self.assertEqual(len(calls), 1)
        request = calls[0][0]
        self.assertEqual(request.full_url, "https://tokenhub.tencentmaas.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "deepseek-v4.1-flash-1017")
        self.assertEqual(payload["web_search_options"], {"enable": True, "search_source": "standard"})
        self.assertEqual(payload["max_tokens"], 16384)

    def test_retry_429_then_success_and_truncation(self):
        sleeps = []
        responses = [
            (429, b'{"error": "rate limit"}'),
            (500, b"oops"),
            (429, b"again"),
            (200, json.dumps({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}).encode()),
        ]

        def fake_transport(request, timeout):
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(Path(tmp))
            result = llm.chat(
                "L1",
                [{"role": "user", "content": "hi"}],
                config=cfg,
                transport=fake_transport,
                sleep=sleeps.append,
                run_log=False,
            )
        self.assertEqual(result["content"], "ok")
        self.assertEqual(sleeps, [2, 4, 8])

        def truncated(request, timeout):
            return 200, json.dumps(
                {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
            ).encode()

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(Path(tmp))
            with self.assertRaises(llm.LLMError) as ctx:
                llm.chat("L1", [{"role": "user", "content": "hi"}], config=cfg, transport=truncated, run_log=False)
        self.assertIn("truncated", str(ctx.exception))


class PreflightTests(unittest.TestCase):
    def test_layers_and_missing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = write_env(
                root,
                "TOKENHUB_API_KEY=a\nHUNYUAN_MODEL_ID=m1\n"
                "DASHSCOPE_API_KEY=b\nQWEN_MODEL_ID=m2\n"
                "DEEPSEEK_API_KEY=\nDEEPSEEK_MODEL_ID=m3\n",
            )
            cfg = config.Config.from_files([env])
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (bin_dir / "ffmpeg").write_text("", encoding="utf-8")
            (bin_dir / "ffprobe").write_text("", encoding="utf-8")
            blockers = root / "BLOCKERS.md"
            result = preflight.run(config_obj=cfg, bin_dir=bin_dir, blockers_path=blockers)
            self.assertFalse(result["ok"])
            self.assertIn("DEEPSEEK_API_KEY", result["missing"])
            self.assertTrue(result["tools"]["ffmpeg"])
            text = blockers.read_text(encoding="utf-8")
            self.assertIn("B-", text)
            self.assertIn("DEEPSEEK_API_KEY", text)
            # 再跑一次不得覆盖已有条目
            preflight.run(config_obj=cfg, bin_dir=bin_dir, blockers_path=blockers)
            self.assertEqual(blockers.read_text(encoding="utf-8").count("DEEPSEEK_API_KEY"), 2)


if __name__ == "__main__":
    unittest.main()
