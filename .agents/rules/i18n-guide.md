# 国际化 (i18n) 规范

## 框架

- **核心**：i18next
- **React 集成**：react-i18next
- **语言文件**：`frontend/src/i18n/en.json`（英文）+ `frontend/src/i18n/zh.json`（中文）
- **初始化**：`frontend/src/i18n/index.ts`

## 语言检测

优先级：`localStorage('sharp-gui-lang')` → 浏览器语言 → 默认英文

## 核心规则

### 1. 必须同步维护中英文

添加任何用户可见文本时，**必须同时** 在 `en.json` 和 `zh.json` 中添加对应的 key-value。

```json
// ✅ 正确 — 两个文件同时添加
// en.json
{ "myNewFeature": "New Feature" }

// zh.json
{ "myNewFeature": "新功能" }
```

```json
// ❌ 错误 — 只在一个文件中添加
// en.json
{ "myNewFeature": "New Feature" }
// zh.json 中缺少对应 key
```

### 2. Key 命名规范

新 key **统一使用 `camelCase`**：

```json
// ✅ 正确
"generateNew": "Generate New",
"loadingModel": "Loading model...",
"deleteConfirm": "Are you sure?"

// ❌ 错误 — 不要使用 snake_case 或 kebab-case
"generate_new": "...",
"loading-model": "..."
```

> **⚠️ 历史遗留**：`controls_view_front`、`controls_view_reset` 等使用了 `snake_case`。这些是历史遗留，不要求修改，但请勿在新 key 中延续此风格。

### 3. Key 分组建议

按功能模块组织 key，使用前缀区分：

```json
{
  "appTitle": "Sharp GUI",
  "generateNew": "Generate New",
  "gallery": "Gallery",
  "galleryEmpty": "No items yet",
  "taskPending": "Pending",
  "taskRunning": "Processing...",
  "settingsTitle": "Settings",
  "settingsWorkspace": "Workspace Folder",
  "viewerReset": "Reset View",
  "viewerFullscreen": "Fullscreen"
}
```

本地媒体图库沿用历史 `photo*` 前缀，例如 `photoGallery`、`photoSortModifiedNewest`、`photoGridDensityStandard`、`photoOriginalLoadFailed`；新增视频/媒体文案也优先放在该前缀下，例如 `photoMediaTypeVideo`、`photoVideoPlaybackFailed`、`photoVideoDownload`。排序、弹窗、错误提示、按钮 tooltip 和 aria-label 都必须双语同步。

模型资产库统一使用 `modelAsset*` 前缀，例如 `modelAssetSourceFilter`、`modelAssetImportFailed`、`modelAssetDeleteConfirm`。标题、筛选、排序、字段、导入进度、逐文件失败、空/不可用状态、权限原因、tooltip 和 aria-label 都必须双语同步；不要新增同义的 `asset*` 或 `modelLibrary*` 前缀。

后端 `error` 文本只用于诊断，用户界面应优先按稳定 `code` 映射当前语言，未知错误使用本地化通用兜底。批量接口的每个 `failed[]` 项都按自己的错误码独立本地化，并保留安全的文件名上下文；不得直接展示后端英文、`Unknown error` 或 `HTTP error! status: 400`。

局域网门禁新增文案统一使用 `access*` / `auth*` 前缀，例如 `accessGateTitle`、`accessSetupPromptTitle`、`authPermissionOwnerOnly`。门禁页、启动提醒、设置说明、错误提示和按钮文案都必须双语同步。

---

## 使用方式

### 在组件中使用

```typescript
import { useTranslation } from 'react-i18next';

export function MyComponent() {
  const { t } = useTranslation();

  return (
    <div>
      <h1>{t('appTitle')}</h1>
      <p>{t('galleryEmpty')}</p>
    </div>
  );
}
```

### 带参数插值

```json
// en.json
{ "itemCount": "{{count}} items" }

// zh.json
{ "itemCount": "共 {{count}} 项" }
```

```typescript
t('itemCount', { count: 5 })  // → "5 items" 或 "共 5 项"
```

### 切换语言

```typescript
import { toggleLanguage } from '@/i18n';

// 在按钮点击时调用
toggleLanguage();
```

`toggleLanguage()` 函数在 `i18n/index.ts` 中导出，自动在 `en` ↔ `zh` 之间切换并持久化到 `localStorage`。

---

## 语言文件位置

```
frontend/src/i18n/
├── index.ts     # i18n 初始化配置 + toggleLanguage 函数
├── en.json      # 英文翻译（约 260+ 个 key）
└── zh.json      # 中文翻译（约 260+ 个 key）
```

## 检查清单

添加 i18n key 后，请确认：

- [ ] `en.json` 和 `zh.json` 都添加了相同的 key
- [ ] key 使用 `camelCase` 命名
- [ ] 翻译内容准确、自然
- [ ] 组件中使用 `t('key')` 而非硬编码文本
- [ ] API 错误和批量失败是否按稳定 `code` 本地化，而非直接显示后端英文或 HTTP 状态
