import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"

/**
 * DevOps Vault — 실제 블로그형 레이아웃.
 *
 * Quartz 기본은 타이틀·검색·다크모드를 좌측 사이드바에 두지만,
 * 여기서는 상단 전체폭 스티키 "헤더"로 옮긴다(styles/custom.scss 가
 * .page-header 를 전체폭 바로 스타일링).
 *
 *   헤더(상단)  : 타이틀 + 검색 + 다크모드 + 리더모드
 *   좌 사이드바 : 카테고리 탐색(Explorer)
 *   우 사이드바 : 목차(TOC) + 백링크
 *   푸터(공통)  : GitHub 링크
 *
 * CI(blog.yml)가 이 파일을 클론한 Quartz 위에 덮어쓴다.
 */

const headerControls = Component.Flex({
  components: [
    { Component: Component.Search(), grow: true },
    { Component: Component.Darkmode() },
    { Component: Component.ReaderMode() },
  ],
})

// 모든 페이지 공통: 상단 헤더 + 푸터
export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [Component.PageTitle(), headerControls],
  afterBody: [],
  footer: Component.Footer({
    links: {
      GitHub: "https://github.com/currentJob/devops-pipeline",
    },
  }),
}

// 단일 노트 페이지
export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.ConditionalRender({
      component: Component.Breadcrumbs(),
      condition: (page) => page.fileData.slug !== "index",
    }),
    Component.ArticleTitle(),
    Component.ContentMeta(),
    Component.TagList(),
  ],
  left: [Component.Explorer()],
  right: [Component.DesktopOnly(Component.TableOfContents()), Component.Backlinks()],
}

// 목록 페이지(태그·폴더)
export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.Breadcrumbs(), Component.ArticleTitle(), Component.ContentMeta()],
  left: [Component.Explorer()],
  right: [],
}
