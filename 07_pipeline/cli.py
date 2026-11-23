"""产品 CLI：preflight / l1-l4。真实 API 只在对应子命令触发。"""

from __future__ import annotations

import argparse
import json
import sys

import audit
import compose
import config as config_module
import l1
import l2
import l3
import l4
import l5
import llm
import preflight
from errors import PipelineError


def _print_summary(title: str, summary: dict) -> None:
    print(f"{title} 完成")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="《五境试炼》产品流水线 Phase 1")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("l1", "采集专业数据并写 01_data"),
        ("l2", "生成单集剧本并写 02_script/episodes"),
        ("l3", "生成分镜三表并写 03_storyboard/EP01"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--episode", default="EP01")
        cmd.add_argument("--resume", action="store_true")
        if name == "l1":
            cmd.add_argument("--major", default="computer")

    l4_cmd = sub.add_parser("l4", help="生成单镜提示词包并写 04_prompts/EP01")
    l4_cmd.add_argument("--episode", default="EP01")
    l4_cmd.add_argument("--batch", type=int, default=4)
    l4_cmd.add_argument("--resume", action="store_true")
    l4_cmd.add_argument("--refresh-lock", action="store_true")

    l5_cmd = sub.add_parser("l5", help="媒体编排：关键帧/视频/配音")
    l5_sub = l5_cmd.add_subparsers(dest="l5_command", required=True)
    keyframes = l5_sub.add_parser("keyframes", help="生成关键帧")
    keyframes.add_argument("--episode", default="EP01")
    keyframes.add_argument("--shots", default=None, help="逗号分隔，如 S001,S002；默认全部")
    keyframes.add_argument("--resume", action="store_true")
    clips = l5_sub.add_parser("clips", help="逐镜图生视频")
    clips.add_argument("--episode", default="EP01")
    clips.add_argument("--shots", default=None, help="逗号分隔，如 S001,S002；默认全部")
    clips.add_argument("--resume", action="store_true")
    tts_cmd = l5_sub.add_parser("tts", help="台词配音")
    tts_cmd.add_argument("--episode", default="EP01")
    tts_cmd.add_argument("--dialogue", default=None, help="逗号分隔，如 D001,D002；默认全部")
    tts_cmd.add_argument("--all", action="store_true", dest="all_dialogue")
    tts_cmd.add_argument("--resume", action="store_true")

    comp = sub.add_parser("compose", help="合成最终 MP4")
    comp.add_argument("--episode", default="EP01")
    comp.add_argument("--version", type=int, default=1)
    comp.add_argument("--allow-silent-bgm", action="store_true")

    val = sub.add_parser("validate", help="校验成片")
    val.add_argument("kind", choices=["final"])
    val.add_argument("path")

    l6_cmd = sub.add_parser("l6", help="质检并写审计报告")
    l6_cmd.add_argument("--episode", default="EP01")
    l6_cmd.add_argument("--final", default=None)

    pre = sub.add_parser("preflight", help="检查 env 键、routing 与 ffmpeg")
    pre.add_argument("--episode", default="EP01")
    pre.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight.run(episode=args.episode)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"episode={result['episode']} ok={result['ok']}")
                for layer, info in result["layers"].items():
                    print(f"{layer} {info['keys']}")
                print(f"routing={result['routing']} tools={result['tools']}")
            return 0 if result["ok"] else 2

        cfg = config_module.load_config()
        if args.command == "l1":
            summary = l1.run(
                episode=args.episode,
                major_en=args.major,
                resume=args.resume,
                config_obj=cfg,
            )
            _print_summary("L1", summary)
            return 0
        if args.command == "l2":
            summary = l2.run(episode=args.episode, resume=args.resume, config_obj=cfg)
            _print_summary("L2", summary)
            return 0
        if args.command == "l3":
            summary = l3.run(episode=args.episode, resume=args.resume, config_obj=cfg)
            _print_summary("L3", summary)
            return 0
        if args.command == "l4":
            if args.refresh_lock:
                summary = l4.refresh_lock()
                _print_summary("L4 refresh-lock", summary)
                return 0
            summary = l4.run(
                episode=args.episode,
                batch=args.batch,
                resume=args.resume,
                config_obj=cfg,
            )
            _print_summary("L4", summary)
            return 0
        if args.command == "l5":
            if args.l5_command == "keyframes":
                summary = l5.keyframes(
                    shots_raw=args.shots,
                    resume=args.resume,
                    config_obj=cfg,
                )
                _print_summary("L5 keyframes", summary)
                return 0
            if args.l5_command == "clips":
                summary = l5.clips(
                    shots_raw=args.shots,
                    resume=args.resume,
                    config_obj=cfg,
                )
                _print_summary("L5 clips", summary)
                return 0
            if args.l5_command == "tts":
                summary = l5.tts(
                    dialogue_raw=args.dialogue,
                    all_dialogue=args.all_dialogue,
                    resume=args.resume,
                    config_obj=cfg,
                )
                _print_summary("L5 tts", summary)
                return 0
        if args.command == "compose":
            summary = compose.compose(version=args.version, allow_silent_bgm=args.allow_silent_bgm)
            _print_summary("compose", summary)
            return 0
        if args.command == "validate":
            errors = compose.validate_final(config_module.PROJECT_ROOT / args.path)
            if errors:
                for error in errors:
                    print(f"[error] {error}", file=sys.stderr)
                return 5
            print("[validate] final: OK")
            return 0
        if args.command == "l6":
            summary = audit.run(final_path=args.final)
            _print_summary("L6", summary)
            return 0 if summary["verdict"] == "PASS" else 5
    except PipelineError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return exc.code
    except config_module.ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    except llm.LLMError as exc:
        print(f"ERROR: LLM 调用失败（{exc.summary}）", file=sys.stderr)
        return 6
    except compose.ComposeError as exc:
        print(f"ERROR: 合成失败（{exc}）", file=sys.stderr)
        return 5
    return 1


if __name__ == "__main__":
    sys.exit(main())
