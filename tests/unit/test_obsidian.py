"""Obsidian vault 도구(vault_save / vault_search) 단위 테스트.

filesystem.WORKSPACE 를 임시 디렉토리로 monkeypatch 하여 호스트와 격리.
"""

from __future__ import annotations

import pytest

from app import config
from app.tools import filesystem, obsidian


@pytest.fixture(autouse=True)
def _temp_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "WORKSPACE", tmp_path)
    # 벡터 인덱스 비활성 → vault_search 는 키워드, vault_save 인덱싱은 no-op (네트워크 없이 격리)
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", False)
    return tmp_path / "vault"


# ── vault_save ────────────────────────────────────────────────────────────────


def test_save_creates_note_with_frontmatter(_temp_vault):
    result = obsidian.vault_save(
        "Rust 비동기", "본문 내용", tags="type/research, tech/rust", aliases="러스트"
    )
    assert "저장 완료" in result
    note = _temp_vault / "Rust 비동기.md"
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'title: "Rust 비동기"' in text
    # 계층형 중첩 태그는 YAML 블록 리스트로 렌더 (Obsidian 프로퍼티 친화)
    assert "tags:\n  - type/research\n  - tech/rust" in text
    assert "aliases:\n  - 러스트" in text
    assert "created:" in text and "updated:" in text
    assert "source: devops-pipeline" in text
    assert "본문 내용" in text


def test_save_empty_tags_aliases_render_empty_list(_temp_vault):
    obsidian.vault_save("태그없음", "내용")
    text = (_temp_vault / "태그없음.md").read_text(encoding="utf-8")
    assert "tags: []" in text
    assert "aliases: []" in text


def test_save_category_subfolder(_temp_vault):
    obsidian.vault_save("트렌드 2026", "내용", category="IT 트렌드")
    assert (_temp_vault / "IT 트렌드" / "트렌드 2026.md").is_file()


def test_save_dedup_suffix(_temp_vault):
    obsidian.vault_save("같은 제목", "첫번째")
    result2 = obsidian.vault_save("같은 제목", "두번째")
    assert "같은 제목-2.md" in result2
    assert (_temp_vault / "같은 제목.md").is_file()
    assert (_temp_vault / "같은 제목-2.md").is_file()


def test_save_empty_title_rejected(_temp_vault):
    result = obsidian.vault_save("   ", "내용")
    assert "저장 거부" in result


def test_save_unsafe_title_sanitized(_temp_vault):
    # 금지문자만으로 이뤄진 제목 → 안전한 파일명 불가
    result = obsidian.vault_save("<>:/\\|?*", "내용")
    assert "저장 거부" in result


def test_save_size_limit(_temp_vault):
    huge = "x" * (filesystem.MAX_FILE_BYTES + 1)
    result = obsidian.vault_save("큰 노트", huge)
    assert "저장 거부" in result


def test_save_category_traversal_contained(_temp_vault):
    obsidian.vault_save("탈출시도", "내용", category="../../etc")
    # category 의 구분자/.. 가 제거되어 vault 밖으로 못 나감
    created = list(_temp_vault.rglob("탈출시도.md"))
    assert len(created) == 1
    assert str(created[0]).startswith(str(_temp_vault))


# ── vault_search ──────────────────────────────────────────────────────────────


def test_search_empty_vault(_temp_vault):
    result = obsidian.vault_search("아무거나")
    assert "기존 노트 없음" in result


def test_search_finds_match(_temp_vault):
    obsidian.vault_save("WebGPU 정리", "브라우저 GPU 컴퓨팅", category="IT 트렌드")
    result = obsidian.vault_search("WebGPU")
    assert "WebGPU 정리.md" in result


def test_search_no_match(_temp_vault):
    obsidian.vault_save("Rust 노트", "내용")
    result = obsidian.vault_search("코틀린스프링")
    assert "매칭되는 기존 노트 없음" in result
