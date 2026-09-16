# CurrentJob Engineering 블로그 (Quartz v4)

`vault/`의 발행 노트와 외부 하네스에서 명시적으로 승인한 글을 `site/content/`에 모아 공개한다.
공개 URL은 저장용 경로를 그대로 드러내지 않고 **카테고리 한 단계 + 글 파일**로 유지한다.

## 공개 정책 (핵심)

`vault/` 는 `.gitignore`(비공개, .env 취급)이라 git 에 올라가지 않는다. 대신:

1. 노트 frontmatter 에 **`publish: true`** 추가
2. `python scripts/publish_vault.py` 실행 → 발행 노트만 **`site/content/`**(git 추적)로 복사
3. `site/content/` 커밋·푸시 → [`blog.yml`](../.github/workflows/blog.yml) 이 Quartz 로 빌드·배포

### 발행 표시 방법

- **로컬**: 노트 frontmatter 에 `publish: true` 직접 추가(또는 Obsidian Properties 체크박스).
- **Telegram `/notes`**: 노트를 카테고리별로 나열해 ✅/⬜ 버튼으로 토글 → `🚀 발행 적용` 누르면
  위 2~3 단계(export + `site/content` 커밋 + push)를 봇이 자동 수행. 발행 적용은 push 까지 가므로
  인라인 확인 1단계를 거친다(워커에 `GITHUB_TOKEN` 필요).

```
vault/ (비공개)            site/content/ (git 추적)        GitHub Pages
  publish:true 노트  ──export──▶  카테고리/글.md ──push→Quartz──▶ 사이트
  승인된 외부 글     ──publish─▶  카테고리/글.md ────────────────▶
```

→ **미발행 노트는 git 에 절대 올라가지 않는다.** (public repo 안전)

```yaml
---
title: "..."
publish: true        # ← 이 줄이 있어야 export 대상
tags: [tech/qdrant]
---
```

- `_` 로 시작하는 생성물(MOC/Dashboard), `digests/` 폴더 → export 제외
- 공개 카테고리는 최상위 한 단계만 사용한다. 기존 `IT 트렌드/`는 `트렌드/`, `생활요리/`는 `라이프/`로 정규화한다.
- `.vault-export-manifest.json`에 기록된 vault 소유 파일만 다음 export에서 교체한다. 외부 하네스가 게시한 글은 보존한다.
- 계층 태그(`type/`·`area/`·`tech/`) → 태그 페이지
- 홈페이지 `index.md`는 편집자가 관리하며, 없을 때만 기본 홈페이지를 생성한다.

## 구성

- [`quartz.config.ts`](quartz.config.ts) — Quartz 설정(우리가 관리). Quartz 본체는 CI에서 검증한 커밋으로 고정해 가져온다.
- [`styles/custom.scss`](styles/custom.scss) — 모던 테크 디자인·애니메이션 커스텀 CSS. CI 가 클론한 Quartz 의 `quartz/styles/custom.scss` 로 덮어쓴다.
- `content/` — 여러 승인 게시 경로가 공유하는 공개 콘텐츠 계층. 각 게시자는 자신이 소유한 파일만 갱신한다.
- 빌드·배포 — [`.github/workflows/blog.yml`](../.github/workflows/blog.yml)

## 최초 1회 설정

레포 **Settings → Pages → Source** 를 **"GitHub Actions"** 로 지정.
배포 URL: `https://currentjob.github.io/devops-pipeline` (변경 시 [`quartz.config.ts`](quartz.config.ts) 의 `baseUrl`).

## 로컬 미리보기

```bash
python scripts/publish_vault.py                       # vault → site/content
git clone --branch v4 https://github.com/jackyzha0/quartz.git /tmp/quartz
cp site/quartz.config.ts /tmp/quartz/quartz.config.ts
cp site/quartz.layout.ts /tmp/quartz/quartz.layout.ts
cp site/styles/custom.scss /tmp/quartz/quartz/styles/custom.scss   # 모던 테크 스타일/애니메이션
rm -rf /tmp/quartz/content && cp -r site/content /tmp/quartz/content
cd /tmp/quartz && npm i && npx quartz build --serve   # http://localhost:8080
```
