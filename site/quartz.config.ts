import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * KBMS 站点配置（Quartz 4.5.x）
 *
 * 内容来源是 `kb.py publish` 生成的 `.publish/`，只含卡片 / MOC / 专题。
 * 这里的 ignorePatterns 是第二道防线：即使有人误把整库当内容目录，也不会发布工作面。
 */
const baseUrl = (process.env.QUARTZ_BASE_URL ?? "localhost:8080").replace(/^https?:\/\//, "")

const config: QuartzConfig = {
  configuration: {
    pageTitle: "KBMS · 个人知识库",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "zh-CN",
    baseUrl,
    ignorePatterns: [
      ".obsidian",
      "90_Meta",
      "00_Inbox",
      "10_Raw",
      "20_Staging",
      "60_Candidates",
      "70_Audit",
    ],
    defaultDateType: "modified",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        header: "Noto Serif SC",
        body: "Noto Sans SC",
        code: "JetBrains Mono",
      },
      colors: {
        lightMode: {
          light: "#fbfaf7",
          lightgray: "#e8e4dc",
          gray: "#a9a29a",
          darkgray: "#4a4640",
          dark: "#23211e",
          secondary: "#2f5d50",
          tertiary: "#8a6f3e",
          highlight: "rgba(47, 93, 80, 0.12)",
          textHighlight: "#e9d98a88",
        },
        darkMode: {
          light: "#17181a",
          lightgray: "#2c2e31",
          gray: "#6f7175",
          darkgray: "#c9c6c0",
          dark: "#ece9e3",
          secondary: "#8fb9a8",
          tertiary: "#c8a86a",
          highlight: "rgba(143, 185, 168, 0.15)",
          textHighlight: "#8f7b2a88",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ["frontmatter", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({
        theme: {
          light: "github-light",
          dark: "github-dark",
        },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "absolute" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: true,
        enableRSS: true,
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.NotFoundPage(),
    ],
  },
}

export default config
