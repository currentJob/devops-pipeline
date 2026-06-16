"""평가 결과 집계 → 마크다운 리포트 + 전체 통과 여부."""

from __future__ import annotations


def build_report(results: list[dict], mode: str) -> tuple[str, bool]:
    """결과 리스트 → (마크다운, 전체통과).

    각 result: {id, route, failures: list[str], judge: dict|None}
    전체통과 = 결정론 위반 0 AND (라이브 시) judge 미달 0.
    """
    det_fail = sum(1 for r in results if r["failures"])
    judged = [r for r in results if r.get("judge") and not r["judge"].get("skipped")]
    judge_fail = sum(1 for r in judged if not r["judge"]["passed"])
    all_passed = det_fail == 0 and judge_fail == 0

    lines = [
        f"# 에이전트 평가 리포트 ({mode})",
        "",
        f"- 시나리오: {len(results)}개",
        f"- 결정론 위반: **{det_fail}**개",
    ]
    if mode == "live":
        scores = [r["judge"]["score"] for r in judged]
        avg = f"{sum(scores) / len(scores):.1f}" if scores else "—"
        lines.append(f"- 품질 채점: {len(judged)}개, 미달 **{judge_fail}**개, 평균 {avg}/5")
    lines += ["", "| 시나리오 | route | 결정론 | 품질 |", "|---|---|---|---|"]

    for r in results:
        det = "✅" if not r["failures"] else "❌ " + "; ".join(r["failures"])
        jr = r.get("judge")
        if not jr or jr.get("skipped"):
            quality = "—"
        else:
            mark = "✅" if jr["passed"] else "❌"
            quality = f"{mark} {jr['score']}/5 (≥{jr['threshold']})"
        lines.append(f"| {r['id']} | {r['route']} | {det} | {quality} |")

    # 품질 채점 근거(라이브)
    if mode == "live" and judged:
        lines += ["", "## 품질 채점 근거", ""]
        for r in judged:
            jr = r["judge"]
            lines.append(f"- **{r['id']}** {jr['score']}/5 — {jr['reason']}")

    return "\n".join(lines) + "\n", all_passed
