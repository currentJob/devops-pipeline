import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * devops-pipeline vault → 기술 블로그 (Quartz v4)
 *
 * CI(.github/workflows/blog.yml)가 Quartz 클론 위에 이 파일을 덮어쓰고,
 * content = 레포의 vault/ 로 빌드한다.
 *
 * 공개 정책: frontmatter 에 `publish: true` 인 노트만 게시(ExplicitPublish).
 *   - 플래그 없는 노트, `_` 생성물, digests/ 는 게시되지 않는다.
 * 카테고리: vault 의 폴더(예: "IT 트렌드")가 Explorer 트리 + 폴더 페이지로,
 *           계층 태그(type/·area/·tech/)는 태그 페이지로 자동 노출된다.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "DevOps Vault",
    pageTitleSuffix: "",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "ko-KR",
    baseUrl: "currentjob.github.io/devops-pipeline",
    ignorePatterns: ["private", "templates", ".obsidian", "digests/**", "**/_*"],
    defaultDateType: "created",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        header: "Schibsted Grotesk",
        body: "Inter",
        code: "IBM Plex Mono",
      },
      colors: {
        // 모던 테크 팔레트 — 차분한 뉴트럴 + 블루→시안 액센트.
        // 세부 효과(그라데이션·애니메이션)는 styles/custom.scss 에서.
        lightMode: {
          light: "#fafafa", // 배경
          lightgray: "#e6e8eb", // 경계선/구분선
          gray: "#9ca3af", // 흐린 텍스트(메타)
          darkgray: "#3f4651", // 본문 텍스트
          dark: "#111827", // 제목/강조 텍스트
          secondary: "#2563eb", // 링크/주요 액센트
          tertiary: "#06b6d4", // 호버/보조 액센트
          highlight: "rgba(37, 99, 235, 0.08)", // 코드/하이라이트 배경
          textHighlight: "#2563eb22", // ==형광== 텍스트
        },
        darkMode: {
          light: "#0d1117", // 배경
          lightgray: "#21262d", // 경계선/구분선
          gray: "#6e7681", // 흐린 텍스트(메타)
          darkgray: "#c4cdd9", // 본문 텍스트
          dark: "#f0f6fc", // 제목/강조 텍스트
          secondary: "#58a6ff", // 링크/주요 액센트
          tertiary: "#22d3ee", // 호버/보조 액센트
          highlight: "rgba(56, 139, 253, 0.1)", // 코드/하이라이트 배경
          textHighlight: "#58a6ff33", // ==형광== 텍스트
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ["frontmatter", "git", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({
        theme: { light: "github-light", dark: "github-dark" },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts(), Plugin.ExplicitPublish()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({ enableSiteMap: true, enableRSS: true }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.NotFoundPage(),
    ],
  },
}

export default config
