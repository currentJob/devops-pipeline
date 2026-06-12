"""MOC/Dashboard 자동 생성(app.rag.moc) 단위 테스트."""

from __future__ import annotations

from app.rag import moc


def _note(tmp_path, name: str, title: str, tags: list[str]):
    block = "\n".join(f"  - {t}" for t in tags)
    text = f'---\ntitle: "{title}"\ntags:\n{block}\nsource: x\n---\n\n본문 {name}'
    (tmp_path / f"{name}.md").write_text(text, encoding="utf-8")


def test_build_moc_empty(tmp_path):
    assert moc.build_moc(tmp_path) == 0


def test_build_moc_generates_dashboard_and_area_mocs(tmp_path):
    _note(tmp_path, "qdrant", "Qdrant 정리", ["type/research", "area/vector-db", "tech/qdrant"])
    _note(tmp_path, "gha", "GitHub Actions", ["type/doc", "area/devops"])
    _note(tmp_path, "pgv", "pgvector", ["type/research", "area/vector-db"])

    written = moc.build_moc(tmp_path)
    # area 2개(_MOC) + Dashboard 1개 = 3
    assert written == 3
    assert (tmp_path / "_Dashboard.md").is_file()
    assert (tmp_path / "_MOC_vector-db.md").is_file()
    assert (tmp_path / "_MOC_devops.md").is_file()

    vb = (tmp_path / "_MOC_vector-db.md").read_text(encoding="utf-8")
    assert "[[Qdrant 정리]]" in vb
    assert "[[pgvector]]" in vb
    assert "[[GitHub Actions]]" not in vb  # 다른 영역

    dash = (tmp_path / "_Dashboard.md").read_text(encoding="utf-8")
    assert "총 노트: 3개" in dash
    assert "area/vector-db(2)" in dash
    assert "[[_MOC_vector-db]]" in dash
    assert "```dataview" in dash  # Dataview 쿼리 포함


def test_build_moc_skips_generated_notes(tmp_path):
    _note(tmp_path, "real", "진짜 노트", ["area/x"])
    (tmp_path / "_Dashboard.md").write_text("기존 생성물", encoding="utf-8")
    moc.build_moc(tmp_path)
    # _ 접두사 노트는 스캔에서 제외되어 카운트/링크에 안 들어감
    dash = (tmp_path / "_Dashboard.md").read_text(encoding="utf-8")
    assert "총 노트: 1개" in dash
