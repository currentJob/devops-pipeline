# vault 기술 블로그 (Quartz v4)

`vault/` 의 Obsidian 노트 중 **발행 표시한 것만** 정적 사이트로 공개한다. 봇이 쌓은 지식 노트를 카테고리별로 보여주는 기술 블로그.

## 공개 정책 (핵심)

`vault/` 는 `.gitignore`(비공개, .env 취급)이라 git 에 올라가지 않는다. 대신:

1. 노트 frontmatter 에 **`publish: true`** 추가
2. `python scripts/publish_vault.py` 실행 → 발행 노트만 **`site/content/`**(git 추적)로 복사
3. `site/content/` 커밋·푸시 → [`blog.yml`](../.github/workflows/blog.yml) 이 Quartz 로 빌드·배포

```
vault/ (비공개)            site/content/ (git 추적)        GitHub Pages
  publish:true 노트  ──export──▶  발행 노트만   ──push→Quartz──▶  사이트
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
- 카테고리 = vault 폴더 구조 보존(예: `IT 트렌드/`) → Quartz Explorer·폴더 페이지
- 계층 태그(`type/`·`area/`·`tech/`) → 태그 페이지
- 발행 노트에 `index.md` 가 없으면 export 가 기본 홈페이지를 생성

## 구성

- [`quartz.config.ts`](quartz.config.ts) — Quartz 설정(우리가 관리). Quartz 본체는 CI 에서 클론.
- `content/` — `publish_vault.py` 가 생성하는 발행물(git 추적). 직접 편집하지 말 것.
- 빌드·배포 — [`.github/workflows/blog.yml`](../.github/workflows/blog.yml)

## 최초 1회 설정

레포 **Settings → Pages → Source** 를 **"GitHub Actions"** 로 지정.
배포 URL: `https://currentjob.github.io/devops-pipeline` (변경 시 [`quartz.config.ts`](quartz.config.ts) 의 `baseUrl`).

## 로컬 미리보기

```bash
python scripts/publish_vault.py                       # vault → site/content
git clone https://github.com/jackyzha0/quartz.git /tmp/quartz
cp site/quartz.config.ts /tmp/quartz/quartz.config.ts
rm -rf /tmp/quartz/content && cp -r site/content /tmp/quartz/content
cd /tmp/quartz && npm i && npx quartz build --serve   # http://localhost:8080
```
