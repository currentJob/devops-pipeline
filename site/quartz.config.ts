import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * CurrentJob Engineering — 기술 블로그 (Quartz v4)
 *
 * CI(.github/workflows/blog.yml)가 Quartz 클론 위에 이 파일을 덮어쓰고,
 * site/content/의 승인된 게시본을 빌드한다.
 *
 * 공개 정책: frontmatter 에 `publish: true` 인 노트만 게시(ExplicitPublish).
 *   - 플래그 없는 노트, `_` 생성물, digests/ 는 게시되지 않는다.
 * 카테고리: 공개 콘텐츠의 최상위 폴더가 Explorer 트리 + 폴더 페이지로,
 *           계층 태그(type/·area/·tech/)는 태그 페이지로 자동 노출된다.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "CurrentJob Engineering",
    pageTitleSuffix: "",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "ko-KR",
    baseUrl: "currentjob.github.io/devops-pipeline",
    ignorePatterns: [
      "private",
      "templates",
      ".obsidian",
      ".vault-export-manifest.json",
      "digests/**",
      "**/_*",
    ],
    defaultDateType: "created",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        header: "IBM Plex Sans KR",
        body: "IBM Plex Sans KR",
        code: "IBM Plex Mono",
      },
      colors: {
        lightMode: {
          light: "#f6f8fb",
          lightgray: "#dfe5ec",
          gray: "#6b7280",
          darkgray: "#344054",
          dark: "#101828",
          secondary: "#175cd3",
          tertiary: "#0e9384",
          highlight: "rgba(23, 92, 211, 0.08)",
          textHighlight: "#fdb02240",
        },
        darkMode: {
          light: "#0b1220",
          lightgray: "#263244",
          gray: "#98a2b3",
          darkgray: "#d0d5dd",
          dark: "#f2f4f7",
          secondary: "#84adff",
          tertiary: "#5fe9d0",
          highlight: "rgba(132, 173, 255, 0.11)",
          textHighlight: "#fdb02235",
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
