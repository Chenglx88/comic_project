#!/usr/bin/env python3
"""Hook 正负用例自检。

用临时 fixture 通过子进程喂 stdin，断言退出码与 stderr 错误码。
不依赖项目内已有产物；全部 fixture 在临时目录生成。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import _hooklib as lib

HOOKS = Path(__file__).resolve().parent


# ---------------------------------------------------------------- fixtures

LOCK = {
    "version": 1,
    "updated": "2026-11-21",
    "protagonists": {
        "lie": {
            "display_name": "烈",
            "visual_anchors": ["短红发", "琥珀眼", "左眉疤"],
            "palette": {"main": "#B23A2E", "accent": "#F2C14E"},
            "outfit": {"top": "玄色短打", "bottom": "束脚裤"},
            "expressions": ["坚定", "错愕", "微笑", "怒", "沉思"],
            "seed_range": [1000, 2000],
            "reference_images": [],
            "prompt_prefix": "LOCK_LIE_PREFIX",
        },
        "mirror": {
            "display_name": "镜",
            "visual_anchors": ["银白短发", "灰蓝眼", "右耳挂饰"],
            "palette": {"main": "#4A6FA5", "accent": "#D8E2DC"},
            "outfit": {"top": "月白长衫", "bottom": "深色长裤"},
            "expressions": ["平静", "好奇", "担忧", "冷峻", "释然"],
            "seed_range": [3000, 4000],
            "reference_images": [],
            "prompt_prefix": "LOCK_MIRROR_PREFIX",
        },
    },
}

SHOT_HEADER = "shot_id,beat,scene,shot_size,camera_move,duration_sec,action,dialogue_id,prompt_file,reference_shot"
DIALOGUE_HEADER = "dialogue_id,character,text,emotion,duration_sec"
FOLEY_HEADER = "cue_id,shot_id,type,description,timing"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def make_lock(selected: str) -> dict:
    lock = json.loads(json.dumps(LOCK))
    if selected == "undecided":
        for character in lock["protagonists"].values():
            character["seed_range"] = None
            character["prompt_prefix"] = "pending"
            character["reference_images"] = []
    return lock


def setup(tmp: Path, selected: str = "undecided"):
    proj = tmp / "proj"
    for rel in (
        "04_prompts/_shared",
        "04_prompts/EP01",
        "02_script/episodes",
        "03_storyboard/EP01",
        ".state",
    ):
        (proj / rel).mkdir(parents=True, exist_ok=True)
    write_json(proj / "04_prompts/_shared/protagonist.json",
               {"selected": selected, "candidates": ["lie", "mirror"]})
    lock = make_lock(selected)
    write_json(proj / "04_prompts/_shared/character_lock.json", lock)
    return proj, lock


def episode_obj() -> dict:
    return {
        "episode_id": "EP01",
        "major": "计算机科学与技术",
        "major_en": "computer",
        "realm": "机枢城",
        "protagonist": "undecided",
        "logline": "少年在机枢城用算法修复失控的机械傀儡。",
        "beats": [
            {"index": 1, "name": "开场", "start_sec": 0, "end_sec": 18, "summary": "晨雾中的机枢城"},
            {"index": 2, "name": "课程", "start_sec": 18, "end_sec": 118, "summary": "用算法拆解问题"},
            {"index": 3, "name": "就业", "start_sec": 118, "end_sec": 198, "summary": "算法工程师的日常"},
            {"index": 4, "name": "收束", "start_sec": 198, "end_sec": 210, "summary": "修复并留下悬念"},
        ],
        "knowledge_points": [
            {"id": "K1", "title": "算法", "explain": "有限步骤解决问题",
             "misconception": "算法等于代码", "source_ref": "S1"},
            {"id": "K2", "title": "数据结构", "explain": "组织数据的方式",
             "misconception": "越复杂越好", "source_ref": "S2"},
            {"id": "K3", "title": "复杂度", "explain": "衡量增长趋势",
             "misconception": "精确计时", "source_ref": "S3"},
        ],
        "characters": ["烈", "镜"],
        "next_episode_hook": "下一集将进入万象医馆。",
        "continuity": {"prev_summary": "首集", "open_threads": []},
        "sources": [
            {"url": "https://example.edu/cs", "retrieved_at": "2026-11-21", "year": 2026}
        ],
    }


def shots_csv(count: int = 45, duration: float = 4.6667, duplicate: bool = False) -> str:
    rows = []
    for index in range(1, count + 1):
        shot_id = "S001" if duplicate else f"S{index:03d}"
        beat = min(4, (index - 1) // 12 + 1)
        rows.append(
            f"{shot_id},{beat},机枢城,中景,固定,{duration:g},角色动作,,S{index:03d}.json,"
        )
    return SHOT_HEADER + "\n" + "\n".join(rows) + "\n"


def prompt_obj(lock: dict, selected: str = "undecided", *, protagonist=None,
               prompt=None, seed: int = 1500, digest=None) -> dict:
    if selected == "undecided":
        protagonist = protagonist or "undecided"
        digest = digest or "sha256:pending"
        text_prompt = prompt if prompt is not None else "少年站在山巅，晨雾翻涌，2D 动画风格"
    else:
        character = lock["protagonists"][selected]
        protagonist = protagonist or selected
        digest = digest or lib.canonical_digest(lock)
        text_prompt = prompt if prompt is not None else (
            f"{character['prompt_prefix']} 少年站在山巅，晨雾翻涌，2D 动画风格"
        )
    return {
        "shot_id": "S001",
        "protagonist": protagonist,
        "character_lock_ref": "04_prompts/_shared/character_lock.json",
        "character_lock_digest": digest,
        "seed": seed,
        "text2img": {
            "prompt": text_prompt,
            "negative_prompt": "blurry, lowres, extra fingers",
            "params": {"steps": 28},
        },
        "img2video": {
            "prompt": "镜头缓慢推进，衣袂飘动，保持人物一致",
            "first_frame": "06_render/keyframes/EP01_computer_S001_v1.png",
            "last_frame": "",
            "params": {"duration_sec": 4},
        },
        "consistency": {"method": "text2img", "reference_image": ""},
    }


def write_payload(proj: Path, rel: str, content: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": rel, "content": content},
        "cwd": str(proj),
    }


def post_payload(proj: Path, rel: str) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": rel, "content": ""},
        "cwd": str(proj),
    }


def run_hook(script: str, payload, proj: Path, raw: str | None = None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    stdin = raw if raw is not None else json.dumps(payload)
    proc = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
    )
    return proc.returncode, proc.stderr


# ---------------------------------------------------------------- cases


def case_paths_valid(tmp):
    proj, _ = setup(tmp)
    return "guard_paths.py", write_payload(proj, "02_script/episodes/EP01_computer.json", "{}"), proj


def case_paths_bad_name(tmp):
    proj, _ = setup(tmp)
    return "guard_paths.py", write_payload(proj, "02_script/episodes/bad.json", "{}"), proj


def case_paths_traversal(tmp):
    proj, _ = setup(tmp)
    return "guard_paths.py", write_payload(proj, "../escape.json", "x"), proj


def case_paths_root_markdown(tmp):
    proj, _ = setup(tmp)
    return "guard_paths.py", write_payload(proj, "README.md", "# x"), proj


def case_paths_keyframe_underscore(tmp):
    proj, _ = setup(tmp)
    return "guard_paths.py", write_payload(
        proj, "06_render/keyframes/EP01_computer_science_S003_v2.png", "x"), proj


def case_paths_data_bad_name(tmp):
    proj, _ = setup(tmp)
    return "guard_paths.py", write_payload(proj, "01_data/structured/Computer.json", "{}"), proj


def case_lock_pending(tmp):
    proj, lock = setup(tmp, "undecided")
    content = json.dumps(prompt_obj(lock), ensure_ascii=False)
    return "guard_character_lock.py", write_payload(proj, "04_prompts/EP01/S001.json", content), proj


def case_lock_missing_ref(tmp):
    proj, lock = setup(tmp, "undecided")
    data = prompt_obj(lock)
    del data["character_lock_ref"]
    return "guard_character_lock.py", write_payload(
        proj, "04_prompts/EP01/S001.json", json.dumps(data, ensure_ascii=False)), proj


def case_lock_bad_json(tmp):
    proj, _ = setup(tmp)
    return "guard_character_lock.py", write_payload(proj, "04_prompts/EP01/S001.json", "{"), proj


def case_lock_wrong_protagonist(tmp):
    proj, lock = setup(tmp, "lie")
    data = prompt_obj(lock, "lie", protagonist="mirror")
    return "guard_character_lock.py", write_payload(
        proj, "04_prompts/EP01/S001.json", json.dumps(data, ensure_ascii=False)), proj


def case_lock_missing_prefix(tmp):
    proj, lock = setup(tmp, "lie")
    data = prompt_obj(lock, "lie", prompt="少年站在山巅，晨雾翻涌，2D 动画风格")
    return "guard_character_lock.py", write_payload(
        proj, "04_prompts/EP01/S001.json", json.dumps(data, ensure_ascii=False)), proj


def case_lock_seed_out(tmp):
    proj, lock = setup(tmp, "lie")
    data = prompt_obj(lock, "lie", seed=999)
    return "guard_character_lock.py", write_payload(
        proj, "04_prompts/EP01/S001.json", json.dumps(data, ensure_ascii=False)), proj


def case_lock_edit_valid(tmp):
    proj, lock = setup(tmp, "undecided")
    data = prompt_obj(lock)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    write_text(proj / "04_prompts/EP01/S001.json", text)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "04_prompts/EP01/S001.json",
            "old_string": '"seed": 1500',
            "new_string": '"seed": 1501',
        },
        "cwd": str(proj),
    }
    return "guard_character_lock.py", payload, proj


def case_artifacts_episode_valid(tmp):
    proj, _ = setup(tmp)
    rel = "02_script/episodes/EP01_computer.json"
    write_json(proj / rel, episode_obj())
    return "validate_artifacts.py", post_payload(proj, rel), proj


def case_artifacts_episode_invalid(tmp):
    proj, _ = setup(tmp)
    rel = "02_script/episodes/EP01_computer.json"
    write_json(proj / rel, {"episode_id": "EP01"})
    return "validate_artifacts.py", post_payload(proj, rel), proj


def case_artifacts_shots_count(tmp):
    proj, _ = setup(tmp)
    rel = "03_storyboard/EP01/shots.csv"
    write_text(proj / rel, shots_csv(count=10))
    return "validate_artifacts.py", post_payload(proj, rel), proj


def case_artifacts_shots_total(tmp):
    proj, _ = setup(tmp)
    rel = "03_storyboard/EP01/shots.csv"
    write_text(proj / rel, shots_csv(count=25, duration=4))
    return "validate_artifacts.py", post_payload(proj, rel), proj


def case_artifacts_shots_duplicate(tmp):
    proj, _ = setup(tmp)
    rel = "03_storyboard/EP01/shots.csv"
    write_text(proj / rel, shots_csv(count=45, duplicate=True))
    return "validate_artifacts.py", post_payload(proj, rel), proj


def case_artifacts_prompt_invalid(tmp):
    proj, _ = setup(tmp)
    rel = "04_prompts/EP01/S001.json"
    write_json(proj / rel, {"shot_id": "S001"})
    return "validate_artifacts.py", post_payload(proj, rel), proj


CASES = [
    ("paths_valid_episode", case_paths_valid, 0, ""),
    ("paths_bad_episode_name", case_paths_bad_name, 2, "BAD_NAME"),
    ("paths_traversal", case_paths_traversal, 2, "OUTSIDE_ROOT"),
    ("paths_root_markdown", case_paths_root_markdown, 0, ""),
    ("paths_keyframe_underscore", case_paths_keyframe_underscore, 0, ""),
    ("paths_data_bad_name", case_paths_data_bad_name, 2, "BAD_NAME"),
    ("lock_valid_pending", case_lock_pending, 0, ""),
    ("lock_missing_ref", case_lock_missing_ref, 2, "LOCK_MISSING"),
    ("lock_bad_json", case_lock_bad_json, 2, "BAD_JSON"),
    ("lock_wrong_protagonist", case_lock_wrong_protagonist, 2, "LOCK_STALE"),
    ("lock_missing_prefix", case_lock_missing_prefix, 2, "LOCK_PREFIX_MISSING"),
    ("lock_seed_out", case_lock_seed_out, 2, "SEED_OUT_OF_RANGE"),
    ("lock_edit_valid", case_lock_edit_valid, 0, ""),
    ("artifacts_episode_valid", case_artifacts_episode_valid, 0, ""),
    ("artifacts_episode_invalid", case_artifacts_episode_invalid, 2, "error"),
    ("artifacts_shots_count", case_artifacts_shots_count, 2, "镜头数"),
    ("artifacts_shots_total", case_artifacts_shots_total, 2, "总时长"),
    ("artifacts_shots_duplicate", case_artifacts_shots_duplicate, 2, "重复"),
    ("artifacts_prompt_invalid", case_artifacts_prompt_invalid, 2, "error"),
]


def main() -> int:
    failures = 0
    for name, builder, expect_rc, expect_text in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            script, payload, proj = builder(Path(tmp))
            rc, stderr = run_hook(script, payload, proj)
        ok = rc == expect_rc and (expect_text in stderr if expect_text else True)
        if ok:
            print(f"PASS {name} (rc={rc})")
        else:
            failures += 1
            print(f"FAIL {name}: rc={rc}, 期望 {expect_rc}；stderr={stderr.strip()!r}")

    # 畸形 stdin 必须 fail-open
    with tempfile.TemporaryDirectory() as tmp:
        proj, _ = setup(Path(tmp))
        rc, stderr = run_hook("guard_paths.py", None, proj, raw="not-json")
    if rc == 0:
        print("PASS malformed_stdin_fail_open (rc=0)")
    else:
        failures += 1
        print(f"FAIL malformed_stdin_fail_open: rc={rc}；stderr={stderr.strip()!r}")

    total = len(CASES) + 1
    print(f"\n[selftest] {total - failures}/{total} 通过，{failures} 失败")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
