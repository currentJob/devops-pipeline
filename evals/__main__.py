"""평가 하네스 CLI.

  python -m evals --mode replay            # 결정론(무과금) — 라우팅·도구 계약
  python -m evals --mode live --out r.md   # 실 LLM + 품질 채점(과금)
  python -m evals --only code_none_deref   # 단일 시나리오

종료코드: 결정론 위반 또는 (라이브) 품질 미달이 있으면 1.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from pathlib import Path

from evals import checks, harness, report
from evals import judge as judge_mod

_SCEN_DIR = Path(__file__).resolve().parent / "scenarios"


async def _run(mode: str, only: str | None) -> list[dict]:
    results: list[dict] = []
    for path in sorted(_SCEN_DIR.glob("*.json")):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        if only and scenario["id"] != only:
            continue
        trace = await harness.run_scenario(scenario, mode=mode)
        failures = checks.check(scenario, trace)
        judge_result = await judge_mod.judge(scenario, trace) if mode == "live" else None
        results.append(
            {
                "id": scenario["id"],
                "route": trace.route,
                "failures": failures,
                "judge": judge_result,
            }
        )
    return results


def main() -> None:
    ap = argparse.ArgumentParser(prog="evals", description="에이전트 평가/회귀 하네스")
    ap.add_argument("--mode", choices=["replay", "live"], default="replay")
    ap.add_argument("--only", help="단일 시나리오 id 만 실행")
    ap.add_argument("--out", help="마크다운 리포트 저장 경로")
    args = ap.parse_args()

    # Windows 콘솔(cp949)에서 이모지 출력 실패 방지
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results = asyncio.run(_run(args.mode, args.only))
    if not results:
        print("실행된 시나리오가 없습니다.", file=sys.stderr)
        sys.exit(2)

    markdown, all_passed = report.build_report(results, args.mode)
    print(markdown)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
