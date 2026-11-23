"""L1 专业数据：检索、结构化、校验与落盘。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import config as config_module
import jsonutil
import llm
import state
from errors import PipelineError

PROJECT_ROOT = config_module.PROJECT_ROOT
SCHEMA_PATH = PROJECT_ROOT / "00_schema" / "majors.json"
PROMPT_PATH = config_module.PIPELINE_DIR / "prompts" / "L1.md"
RAW_DIR = PROJECT_ROOT / "01_data" / "raw"
STRUCTURED_DIR = PROJECT_ROOT / "01_data" / "structured"
VALIDATOR = PROJECT_ROOT / ".claude" / "scripts" / "validate.py"

SCHEMA_INSTRUCTION = """\
只返回一个 JSON 对象，不要 Markdown 围栏或解释。必须满足：
- 必填 version（写 2）、major、major_en、realm、retrieved_at（YYYY-MM-DD，本次固定为 2026-11-22）。
- courses 恰好 5 条；每条含 name、explain、learning_content（3-5 条）、labs_projects（1-2 条）、abilities（1-2 条）、source_url、year。
- employment.directions 恰好 5 条；每条含 name、explain、main_tasks（3-5 条）、employers（3-5 家）、salary_range（一线城市本科应届税前月薪约数，如「约 15-25K/月」）、abilities（2-3 条）、source_url、year。
- 每条课程、就业方向都必须带 source_url（http/https 开头）与 year（2000-2030 整数）。
- year 是来源发布年份；若 2026 数据未发布，使用最新公开年份并在 year 写该年份，不要编造 2026。
- 不再采集任何导师信息；顶层不得出现 mentors，正文不得写导师画像。
- sources 汇总全部来源，每条含 url、retrieved_at、year。
- 可用来源：院校官网、教育部/学位与研究生教育发展中心公开信息、阳光高考/学职平台、企业招聘页、公开就业报告、薪酬报告。禁止付费墙、登录页、个人隐私。
- 来源质量：课程只允许院校官网培养方案、阳光高考、省级教育考试院；就业只允许国家统计局、教育部、人社部、省级教育考试院、学职平台、麦可思/智联/猎聘等报告原文、双一流高校就业质量报告、企业官方招聘页。禁止用 zhaosheng.com、gaokao.com、eol.cn、sgpjbg.com.cn、百家号、搜狐/网易/知乎等聚合站、门户或自媒体页面作为 source_url。
- 所有 source_url 必须是具体页面（文章/报告/招聘页），不得是站点首页或栏目页。
- 课程：优先经典本科主干课（数据结构与算法、计算机组成原理、操作系统、计算机网络、编译原理、离散数学、数据库系统、软件工程），不要用前沿选修课替代主干课；learning_content 写具体章节/知识点，不写空泛口号。
- 就业：main_tasks 写具体日常工作；employers 以国内雇主为主，可含少量外企；salary_range 只写大致区间，不写年薪总包；每个方向的 source_url 必须是具体岗位/报告/招聘页面。
- 你有联网搜索能力，必须实际检索；不得以「未提供来源清单」或「无法检索」为由返回 BLOCKED。只有检索完全失败才返回 BLOCKED。
"""


def load_major(major_en: str) -> dict:
    majors = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["majors"]
    for item in majors:
        if item.get("major_en") == major_en:
            return item
    raise PipelineError(f"00_schema/majors.json 中找不到专业 {major_en}", code=4)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_year(value) -> bool:
    return _is_int(value) and 2000 <= value <= 2030


FORBIDDEN_SOURCE_HOSTS = (
    "zhaosheng.com",
    "gaokao.com",
    "eol.cn",
    "sgpjbg.com.cn",
    "baijiahao.baidu.com",
    "sohu.com",
    "163.com",
    "zhihu.com",
)


def _is_forbidden_source(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == banned or host.endswith("." + banned) for banned in FORBIDDEN_SOURCE_HOSTS)


def _is_homepage(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path in ("", "/") and not parsed.query


def _check_source(record: dict, where: str, errors: list[str]) -> None:
    url = record.get("source_url")
    if not isinstance(url, str) or not url.startswith("http"):
        errors.append(f"{where}.source_url 必须以 http 开头")
    elif _is_forbidden_source(url):
        errors.append(f"{where}.source_url 不得使用聚合站/自媒体域名")
    elif _is_homepage(url):
        errors.append(f"{where}.source_url 必须是具体页面，不能是首页")
    if not _valid_year(record.get("year")):
        errors.append(f"{where}.year 必须为 2000-2030 整数")


def _check_text_list(value, minimum: int, maximum: int, where: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        actual = len(value) if isinstance(value, list) else "非数组"
        errors.append(f"{where} 必须为 {minimum}-{maximum} 条，实际 {actual}")
        return
    if not all(isinstance(item, str) and item.strip() for item in value):
        errors.append(f"{where} 含空值")


def validate_l1(
    data,
    expected_major_en: str = "computer",
    expected_realm: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"]
    if expected_realm is None:
        expected_realm = load_major(expected_major_en)["realm"]
    for field in ("major", "major_en", "realm", "retrieved_at"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"缺少 {field}")
    if data.get("major_en") != expected_major_en:
        errors.append(f"major_en 应为 {expected_major_en}")
    if data.get("realm") != expected_realm:
        errors.append(f"realm 应为 {expected_realm}")
    retrieved_at = data.get("retrieved_at")
    if isinstance(retrieved_at, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved_at):
        errors.append(f"retrieved_at 必须为 YYYY-MM-DD: {retrieved_at!r}")

    courses = data.get("courses")
    if not isinstance(courses, list) or len(courses) != 5:
        errors.append(f"courses 必须为 5 条，实际 {len(courses) if isinstance(courses, list) else '非数组'}")
    else:
        for index, course in enumerate(courses):
            if not isinstance(course, dict):
                errors.append(f"courses[{index}] 不是对象")
                continue
            if not isinstance(course.get("name"), str) or not course["name"].strip():
                errors.append(f"courses[{index}] 缺 name")
            if not isinstance(course.get("explain"), str) or not course["explain"].strip():
                errors.append(f"courses[{index}] 缺 explain")
            _check_text_list(
                course.get("learning_content"), 3, 5, f"courses[{index}].learning_content", errors
            )
            _check_text_list(
                course.get("labs_projects"), 1, 2, f"courses[{index}].labs_projects", errors
            )
            _check_text_list(course.get("abilities"), 1, 2, f"courses[{index}].abilities", errors)
            _check_source(course, f"courses[{index}]", errors)

    employment = data.get("employment")
    if not isinstance(employment, dict):
        errors.append("缺少 employment")
    else:
        directions = employment.get("directions")
        if not isinstance(directions, list) or len(directions) != 5:
            errors.append(
                f"employment.directions 必须为 5 条，实际 "
                f"{len(directions) if isinstance(directions, list) else '非数组'}"
            )
        else:
            for index, direction in enumerate(directions):
                if not isinstance(direction, dict):
                    errors.append(f"employment.directions[{index}] 必须是对象")
                    continue
                where = f"employment.directions[{index}]"
                if not isinstance(direction.get("name"), str) or not direction["name"].strip():
                    errors.append(f"{where} 缺 name")
                if not isinstance(direction.get("explain"), str) or not direction["explain"].strip():
                    errors.append(f"{where} 缺 explain")
                _check_text_list(direction.get("main_tasks"), 3, 5, f"{where}.main_tasks", errors)
                _check_text_list(direction.get("employers"), 3, 5, f"{where}.employers", errors)
                _check_text_list(direction.get("abilities"), 2, 3, f"{where}.abilities", errors)
                salary = direction.get("salary_range")
                if not isinstance(salary, str) or not salary.strip():
                    errors.append(f"{where}.salary_range 不得为空")
                _check_source(direction, where, errors)
        _check_source(employment, "employment", errors)

    if "mentors" in data:
        errors.append("L1 不再采集导师信息，顶层不得出现 mentors")

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources 至少 1 条")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"sources[{index}] 不是对象")
                continue
            url = source.get("url")
            if not isinstance(url, str) or not url.startswith("http"):
                errors.append(f"sources[{index}].url 必须以 http 开头")
            elif _is_forbidden_source(url):
                errors.append(f"sources[{index}].url 不得使用聚合站/自媒体域名")
            elif _is_homepage(url):
                errors.append(f"sources[{index}].url 必须是具体页面，不能是首页")
            retrieved_at = source.get("retrieved_at")
            if not isinstance(retrieved_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved_at):
                errors.append(f"sources[{index}].retrieved_at 必须为 YYYY-MM-DD")
            if not _valid_year(source.get("year")):
                errors.append(f"sources[{index}].year 必须为 2000-2030 整数")
    return errors


def _messages(major: dict) -> list[dict]:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    system = prompt + "\n\n" + SCHEMA_INSTRUCTION
    user = (
        f"专业：{major['major']}（major_en={major['major_en']}，realm={major['realm']}）\n"
        "目标年份：2026；检索日期：2026-11-22。\n"
        "允许来源：院校官网、教育部/学位与研究生教育发展中心公开信息、阳光高考/学职平台、"
        "企业官方招聘页、公开就业报告、薪酬报告；禁止付费墙、登录页、个人隐私。\n"
        "硬性要求：课程优先经典本科主干课，写具体学习内容、实验/项目与能力；"
        "就业写主要工作、代表公司、一线本科应届月薪约数与能力，代表公司以国内为主；"
        "不再采集导师信息；"
        "禁止 eol.cn、sgpjbg.com.cn 等聚合站/门户；所有来源必须是具体页面而非首页；"
        "请使用联网搜索，按 schema 只返回 JSON；检索不到 2026 数据时用最新公开年份，"
        "不要把缺失当成 BLOCKED。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _outputs(major_en: str) -> tuple[Path, Path]:
    return STRUCTURED_DIR / f"{major_en}.json", RAW_DIR


def write_outputs(data: dict) -> dict:
    major_en = data["major_en"]
    structured_path, raw_dir = _outputs(major_en)
    stamp = state.utc_stamp()
    raw_path = raw_dir / f"{major_en}_L1_{stamp}.json"
    state.write_json(raw_path, data)

    structured = {
        key: data.get(key)
        for key in (
            "version",
            "major",
            "major_en",
            "realm",
            "retrieved_at",
            "courses",
            "employment",
            "sources",
        )
    }
    state.write_json(structured_path, structured)
    return {
        "raw": raw_path,
        "structured": structured_path,
    }


def _run_validator(structured_path: Path) -> tuple[bool, str]:
    """只校验本层产物，避免被尚未重跑的下游 STALE 产物拖累。"""
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "data", str(structured_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output


def _summary(data: dict, paths: dict) -> dict:
    employment = data.get("employment") or {}
    return {
        "major_en": data.get("major_en"),
        "courses": len(data.get("courses") or []),
        "directions": len(employment.get("directions") or []),
        "sources": len(data.get("sources") or []),
        "paths": {name: str(path) for name, path in paths.items()},
    }


def run(
    episode: str = "EP01",
    major_en: str = "computer",
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    major = load_major(major_en)
    structured_path, _ = _outputs(major_en)
    if resume and structured_path.is_file():
        passed, output = _run_validator(structured_path)
        if not passed:
            raise PipelineError("L1 resume 未通过 validate.py data: " + output)
        data = json.loads(structured_path.read_text(encoding="utf-8"))
        errors = validate_l1(data, major_en, major["realm"])
        if errors:
            raise PipelineError("L1 resume 校验失败：" + "; ".join(errors))
        return _summary(data, {"structured": structured_path})

    messages = _messages(major)
    data = None
    errors: list[str] = []
    for attempt in range(3):
        result = llm.chat(
            "L1",
            messages,
            max_tokens=16384,
            config=config_obj,
            episode=episode,
        )
        try:
            data = jsonutil.extract_json(result["content"])
        except ValueError as exc:
            errors = [str(exc)]
        else:
            errors = validate_l1(data, major_en, major["realm"])
            if not errors:
                break
        if attempt < 2:
            messages = messages + [
                {"role": "assistant", "content": result["content"]},
                {
                    "role": "user",
                    "content": "上次输出未通过校验，请只返回修复后的完整 JSON。错误：\n- "
                    + "\n- ".join(errors),
                },
            ]
    if data is None or errors:
        raise PipelineError("L1 校验重试耗尽：" + "; ".join(errors))
    paths = write_outputs(data)
    passed, output = _run_validator(paths["structured"])
    if not passed:
        raise PipelineError("L1 产物未通过 validate.py data: " + output)
    return _summary(data, paths)
