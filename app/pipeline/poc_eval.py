"""PoC 평가 — 정적지표 측정 + LLM 종합 → EVALUATION.md 리포트 생성.

`/pocrun <slug>` 가 pocsandbox 에서 build+run 한 뒤, 그 결과(build_result)와 함께
이 모듈을 호출한다. PoC 소스를 읽어 객관 지표를 측정하고, Claude 로 "무슨 코드/어디
사용/강점/장단점/관점별 점수"를 종합해 worker 작업공간에 EVALUATION.md 로 저장한다.

worker 프로세스에서만 동작한다(`/workspace` 마운트 + Claude 키 보유). bot 은 read-only 라
PoC 파일에 접근할 수 없으므로 평가를 직접 수행하지 못한다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

POC_OUTPUT_SUBDIR = "prompts/output/poc"
REPORT_NAME = "EVALUATION.md"
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

# 평가 관점 (LLM 점수 키 → 한국어 라벨). 0~5점.
RUBRIC: list[tuple[str, str]] = [
    ("functionality", "기능성·완성도"),
    ("code_quality", "코드 품질"),
    ("security", "보안"),
    ("maintainability", "복잡도·유지보수성"),
    ("dependencies", "의존성·공급망"),
    ("runnability", "실행 가능성"),
    ("documentation", "문서화"),
]

# 소스 다이제스트/지표 대상 — 코드·설정·문서 확장자
_TEXT_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".java",
    ".rs",
    ".rb",
    ".php",
    ".sh",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".md",
    ".txt",
}
_CODE_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".java": "Java",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".sql": "SQL",
}
_EXCLUDE_NAMES = {REPORT_NAME}  # 자기 리포트는 지표/소스에서 제외(재평가 오염 방지)
_MAX_FILE_BYTES = 200_000  # 단일 파일 읽기 상한
_SOURCES_CAP = 12_000  # LLM 입력 소스 다이제스트 총 문자 상한
_LOG_CAP = 1500  # 리포트에 싣는 build/run 로그 상한


def valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.fullmatch(slug or ""))


# ── 정적 지표 ────────────────────────────────────────────────────────────────


def _is_dockerfile(p: Path) -> bool:
    return p.name == "Dockerfile" or p.suffix == ".dockerfile"


def _count_services(compose_text: str) -> int:
    """docker-compose.yml 의 services 하위 2-space 들여쓰기 키 수 (yaml 의존성 없이)."""
    in_services = False
    count = 0
    for line in compose_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():  # 최상위 키
            in_services = line.split(":", 1)[0].strip() == "services"
            continue
        if in_services:
            indent = len(line) - len(line.lstrip(" "))
            if indent == 2 and line.rstrip().endswith(":"):
                count += 1
    return count


def collect_metrics(poc_dir: Path) -> dict:
    """PoC 디렉토리의 객관 지표를 측정 (순수·stdlib)."""
    files = [p for p in poc_dir.rglob("*") if p.is_file() and p.name not in _EXCLUDE_NAMES]
    total_loc = 0
    languages: dict[str, int] = {}
    dockerfiles = 0
    deps = 0

    for p in files:
        if _is_dockerfile(p):
            dockerfiles += 1
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
            if p.suffix.lower() in _TEXT_EXTS or _is_dockerfile(p):
                text = p.read_text(encoding="utf-8", errors="replace")
            else:
                continue
        except OSError:
            continue

        loc = len(text.splitlines())
        total_loc += loc
        lang = _CODE_LANG.get(p.suffix.lower())
        if lang:
            languages[lang] = languages.get(lang, 0) + loc
        if p.name == "requirements.txt":
            deps += sum(
                1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")
            )

    services = 0
    compose = poc_dir / "docker-compose.yml"
    has_compose = compose.is_file()
    if has_compose:
        try:
            services = _count_services(compose.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            services = 0
    if services == 0:
        services = dockerfiles  # compose 파싱 실패 시 Dockerfile 수로 대체

    return {
        "file_count": len(files),
        "total_loc": total_loc,
        "services": services,
        "dockerfiles": dockerfiles,
        "dependencies": deps,
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        "has_readme": (poc_dir / "README.md").is_file(),
        "has_handoff": (poc_dir / "HANDOFF.md").is_file(),
        "has_compose": has_compose,
    }


def read_sources(poc_dir: Path, cap: int = _SOURCES_CAP) -> str:
    """LLM 입력용 소스 다이제스트 — 경로 헤더 + 본문, 총 cap 문자로 절단."""
    chunks: list[str] = []
    size = 0
    for p in sorted(poc_dir.rglob("*")):
        if not p.is_file() or p.name in _EXCLUDE_NAMES:
            continue
        if not (p.suffix.lower() in _TEXT_EXTS or _is_dockerfile(p)):
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(poc_dir).as_posix()
        chunk = f"\n# ===== {rel} =====\n{body}"
        if size + len(chunk) > cap:
            chunks.append(f"\n# ===== {rel} =====\n(생략 — 다이제스트 상한 도달)")
            break
        chunks.append(chunk)
        size += len(chunk)
    return "".join(chunks)


# ── LLM 종합 ─────────────────────────────────────────────────────────────────

_SYSTEM = (
    "당신은 PoC(개념증명) 코드 평가 전문가입니다. 주어진 소스·지표·실행결과를 근거로 "
    "냉정하게 평가하고, 지정된 JSON 객체 하나만 출력하세요. 그 외 텍스트 금지."
)


def build_prompt(slug: str, metrics: dict, sources: str, build_result: dict) -> str:
    rubric_keys = ", ".join(k for k, _ in RUBRIC)
    bo = build_result.get("ok")
    build_line = (
        f"build/run: ok={bo}, stage={build_result.get('stage', '-')}\n"
        f"logs(앞부분):\n{(build_result.get('logs') or '')[:_LOG_CAP]}"
    )
    return (
        f"PoC slug: {slug}\n\n"
        f"[정적 지표]\n{json.dumps(metrics, ensure_ascii=False)}\n\n"
        f"[격리 실행 결과]\n{build_line}\n\n"
        f"[소스 다이제스트]\n{sources}\n\n"
        "위 PoC 를 평가해 아래 JSON 만 출력하세요(값은 한국어):\n"
        "{\n"
        '  "what": "무슨 코드인지 2~3문장",\n'
        '  "where": "어디에/어떤 상황에 쓰이는지",\n'
        '  "strengths": ["핵심 강점", ...],\n'
        '  "pros": ["장점", ...],\n'
        '  "cons": ["단점/리스크", ...],\n'
        f'  "scores": {{ {rubric_keys} 각 0~5 정수 }},\n'
        '  "summary": "총평 2~3문장"\n'
        "}\n"
        "scores 는 실행결과(실패/타임아웃이면 runnability 하향)와 지표를 반영하세요."
    )


def parse_llm_json(text: str) -> dict:
    """LLM 출력에서 첫 JSON 객체만 파싱(코드펜스·잡설 무시). 실패 시 빈 dict."""
    cleaned = text.strip()
    start = cleaned.find("{")
    if start < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _scores_from(parsed: dict) -> dict[str, int]:
    """LLM scores(영문 키) → {한국어 라벨: 0~5 정수}. 누락/이상치는 제외."""
    raw = parsed.get("scores") or {}
    out: dict[str, int] = {}
    for key, label in RUBRIC:
        v = raw.get(key)
        if isinstance(v, (int, float)) and 0 <= v <= 5:
            out[label] = int(v)
    return out


def _overall(scores: dict[str, int]) -> float | None:
    return round(sum(scores.values()) / len(scores), 1) if scores else None


# ── 리포트 렌더 ──────────────────────────────────────────────────────────────


def _bullets(items) -> str:
    if not isinstance(items, list) or not items:
        return "- (없음)"
    return "\n".join(f"- {str(x).strip()}" for x in items if str(x).strip())


def render_report(slug: str, metrics: dict, build_result: dict, parsed: dict, llm_ok: bool) -> str:
    scores = _scores_from(parsed)
    overall = _overall(scores)
    langs = ", ".join(f"{k} {v}" for k, v in metrics["languages"].items()) or "-"
    bo = build_result.get("ok")
    build_icon = "✅ 성공" if bo else ("🔴 실패/타임아웃" if bo is not None else "– 미실행")

    lines = [
        f"# PoC 평가 — {slug}",
        "",
        f"_생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## 종합",
        "",
        f"- **종합 점수**: {'⭐ ' + str(overall) + ' / 5' if overall is not None else 'N/A (LLM 미연결)'}",
        f"- **격리 실행**: {build_icon} (stage: {build_result.get('stage', '-')})",
        "",
        "## 관점별 점수",
        "",
        "| 관점 | 점수 |",
        "|------|:----:|",
    ]
    if scores:
        lines += [f"| {label} | {scores[label]} |" for _, label in RUBRIC if label in scores]
    else:
        lines.append("| (LLM 미연결 — 점수 없음) | - |")

    lines += [
        "",
        "## 정적 지표",
        "",
        "| 지표 | 값 |",
        "|------|----|",
        f"| 파일 수 | {metrics['file_count']} |",
        f"| 총 LOC | {metrics['total_loc']} |",
        f"| 서비스 수 | {metrics['services']} |",
        f"| 의존성 수 | {metrics['dependencies']} |",
        f"| 언어 분포(LOC) | {langs} |",
        f"| README / HANDOFF / compose | "
        f"{'✅' if metrics['has_readme'] else '❌'} / "
        f"{'✅' if metrics['has_handoff'] else '❌'} / "
        f"{'✅' if metrics['has_compose'] else '❌'} |",
        "",
        "## 무슨 코드인가",
        "",
        str(parsed.get("what") or "(LLM 미연결 — 정적지표만 측정됨)"),
        "",
        "## 어디에 쓰이는가",
        "",
        str(parsed.get("where") or "-"),
        "",
        "## 강점",
        "",
        _bullets(parsed.get("strengths")),
        "",
        "## 장점",
        "",
        _bullets(parsed.get("pros")),
        "",
        "## 단점·리스크",
        "",
        _bullets(parsed.get("cons")),
        "",
        "## 총평",
        "",
        str(parsed.get("summary") or "(LLM 미연결)"),
        "",
        "## 격리 실행 로그(발췌)",
        "",
        "```",
        (build_result.get("logs") or "(로그 없음)")[:_LOG_CAP],
        "```",
        "",
    ]
    if not llm_ok:
        lines.insert(4, "> ⚠️ LLM 미연결 — 정성 평가 없이 정적지표만 측정했습니다.\n")
    return "\n".join(lines)


def format_telegram_summary(result: dict) -> str:
    """평가 결과 dict → Telegram 요약 텍스트(점수표 + 총평 + 경로)."""
    scores: dict[str, int] = result.get("scores") or {}
    overall = result.get("overall")
    head = f"🧪 *PoC 평가* — `{result.get('slug', '')}`\n"
    head += f"종합 {'⭐ ' + str(overall) + '/5' if overall is not None else 'N/A'}\n"
    body = "\n".join(f"• {label}: {score}" for label, score in scores.items()) or "• (점수 없음)"
    summary = (result.get("summary") or "").strip()
    tail = f"\n\n_{summary[:300]}_" if summary else ""
    return f"{head}{body}{tail}\n\n📄 `{result.get('report_path', '')}`"


# ── 오케스트레이션 (worker 에서 호출) ─────────────────────────────────────────


async def evaluate(poc_dir: Path, slug: str, build_result: dict) -> dict:
    """지표 측정 → LLM 종합 → EVALUATION.md 저장. 결과 요약 dict 반환.

    Claude/vLLM 미연결이거나 LLM 호출 실패 시에도 정적지표만으로 리포트를 생성한다.
    """
    from app import config

    metrics = collect_metrics(poc_dir)
    parsed: dict = {}
    llm_ok = False

    if config.CLAUDE_API_KEY or config.VLLM_ENDPOINT:
        try:
            from app.agent import runtime

            sources = read_sources(poc_dir)
            raw = await runtime.chat(
                system=_SYSTEM, user=build_prompt(slug, metrics, sources, build_result)
            )
            parsed = parse_llm_json(raw)
            llm_ok = bool(parsed)
            if not llm_ok:
                logger.warning("PoC 평가 LLM 응답 JSON 파싱 실패 slug=%s", slug)
        except Exception as e:  # noqa: BLE001 — LLM 실패해도 정적지표 리포트는 생성
            logger.warning("PoC 평가 LLM 호출 실패 slug=%s: %s", slug, e)

    report = render_report(slug, metrics, build_result, parsed, llm_ok)
    (poc_dir / REPORT_NAME).write_text(report, encoding="utf-8")

    scores = _scores_from(parsed)
    return {
        "slug": slug,
        "report_path": f"{POC_OUTPUT_SUBDIR}/{slug}/{REPORT_NAME}",
        "overall": _overall(scores),
        "scores": scores,
        "summary": parsed.get("summary", ""),
        "llm_ok": llm_ok,
        "metrics": metrics,
    }
