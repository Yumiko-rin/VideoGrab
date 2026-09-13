# VideoGrab — 设计系统 MASTER

> 由 [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) 检索生成，
> 综合查询：`--domain style "glassmorphism translucent frosted"`（玻璃拟态材质规范）、
> `--design-system "video downloader media tool"`（字体/特效/交付清单）、
> 并融合 Apple **Liquid Glass** 设计语言（WWDC 2025）的材质与层次特征。
> 本文件是全局唯一视觉规范（Source of Truth），所有页面/组件必须引用此处 token。

## 1. 产品定位

- **类型**：工具类（Tool）+ 媒体娱乐混合
- **核心场景**：粘贴链接 → 解析 → 选清晰度 → 下载，全程 < 3 次点击
- **风格关键词**：liquid glass, translucent, layered, airy, premium, Apple-like

## 2. 风格：Liquid Glass（液态玻璃 · 浅色）

| 属性 | 值 |
|---|---|
| 材质 | 半透明白 + `backdrop-filter: blur(22px) saturate(180%)` |
| 背景 | 浅色渐变网底（多彩模糊色斑），玻璃层必须有色彩可供折射 |
| 边框 | 1px 亮边 `rgba(255,255,255,.7)` + 顶部镜面高光 `inset 0 1px 0 rgba(255,255,255,.85)` |
| 阴影 | 柔和弥散 `0 8px 32px rgba(31,41,55,.10)`，禁止生硬黑影 |
| 对比 | 正文文字对比度 ≥ 4.5:1（深灰文字于浅玻璃之上） |
| 层次 | 背景 mesh → 玻璃卡片 → 悬浮控件，三层 z-depth |

## 3. 色彩 Token

| Token | 值 | 用途 |
|---|---|---|
| `--color-bg` | `#F2F3F7` | 页面基底（近白） |
| `--color-glass` | `rgba(255,255,255,.55)` | 玻璃面板 |
| `--color-glass-strong` | `rgba(255,255,255,.75)` | 悬浮导航/激活态 |
| `--color-border` | `rgba(255,255,255,.7)` | 玻璃亮边 |
| `--color-text` | `#1D1D1F` | 主文字（Apple 墨灰） |
| `--color-text-muted` | `#5C6068` | 次级文字（白底 5.1:1） |
| `--color-accent` | `#0071E3` | CTA/主操作（Apple Blue） |
| `--color-accent-hover` | `#0077ED` | CTA 悬停 |
| `--color-on-accent` | `#FFFFFF` | 蓝底文字 |
| `--grad-brand` | `linear-gradient(135deg, #0A84FF, #6366F1)` | Logo、进度条、品牌渐变 |
| `--grad-text` | `linear-gradient(120deg, #0A84FF, #6366F1 55%, #EC4899)` | Hero 标题高亮 |
| `--color-success` | `#067647` | 完成（浅绿底 `rgba(52,199,89,.16)`） |
| `--color-destructive` | `#B3261E` | 错误/取消 |

背景 mesh 色斑（供玻璃折射，低饱和）：靛蓝 `rgba(99,102,241,.38)` · 粉 `rgba(236,72,153,.30)` · 天蓝 `rgba(56,189,248,.34)` · 橙 `rgba(249,115,22,.26)`。

## 4. 字体

- **西文**：`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "Inter"`——优先系统字体，最接近 Apple 质感
- **中文回退**：`"PingFang SC", "Microsoft YaHei", sans-serif`
- **规格**：正文 16px / 行高 1.5；Hero 标题 32px+（clamp 至 44px），字重 700-800，字距 -0.03em；数据（速度/大小/时长）用 `"JetBrains Mono", ui-monospace`

## 5. 造型与动效

- **形状语言**：胶囊（按钮/输入框/chips `border-radius: 999px`）+ 大同心圆角（卡片 24px）
- **悬浮导航**：sticky 顶部胶囊玻璃条，居中悬浮
- **分段控件**：iOS 风格 segmented control——灰玻璃槽 + 白色浮起激活片
- **过渡**：260ms `cubic-bezier(.34,.69,.28,1)`（弹簧感）；hover 用 `scale(1.02~1.03)` 代替位移
- **CTA 光晕**：`0 8px 24px rgba(10,132,255,.35)`，克制使用
- **必须**响应 `prefers-reduced-motion: reduce`

## 6. 布局

- 移动优先断点：375 / 768 / 1024 / 1440
- 内容最大宽度 760px（单栏工具流），大屏居中
- 区块间距 48px+，卡片内边距 24px

## 7. UX 硬规则（来自 ux-guidelines.csv，与主题无关恒定）

1. 长任务必须有**进度条 + 百分比 + 速度 + ETA**（Feedback / Progress Indicators）
2. 长标题**截断 + 展开显示全文**（Content / Truncation）
3. 表单**失焦即校验**，不只提交时校验（Forms / Inline Validation）
4. 错误信息**就近显示在字段下方**，`aria-describedby` 关联（Forms / Error Placement）
5. 全部图标用内联 SVG（Lucide 线条风格），**禁止 emoji 当图标**
6. 所有可点元素 `cursor: pointer` + 可见 `:focus-visible` 描边
7. 按钮最小触达 44×44px，间距 ≥ 8px

## 8. 玻璃拟态实现清单（来自 styles.csv）

- [x] `backdrop-filter: blur(10-20px)`（本系统 22px + saturate 180%）
- [x] 半透明白叠层 15–75%
- [x] 1px 亮色边框
- [x] 鲜活背景验证（彩色 mesh 承托，玻璃折射可见）
- [x] 文字对比度 ≥ 4.5:1
- [x] `-webkit-backdrop-filter` 兼容前缀
