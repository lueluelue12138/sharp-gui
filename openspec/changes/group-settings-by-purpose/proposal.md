## Why

设置页已叠加工作区、全局配置、图库缓存、视频、查看器、门禁和更新功能，单列长滚动难以查找。需要按用途组织，同时保持既有组件风格、权限和保存语义。

## What Changes

- 六个明确分组：常规、访问与安全、查看器、图库、视频重建、更新中心；桌面侧边导航，窄屏紧凑顶部导航。
- 复用现有设置控件、通用 Button、配置恢复与更新组件，保持玻璃态和双语文案。
- 分组间保留草稿，底部统一保存并显示未保存状态；缓存/诊断/更新按进入分组加载，避免刷新覆盖视频草稿。
- 验证本机与远程权限、键盘导航、桌面/窄屏布局与保存行为。
- 不新增设置项、不改后端 API、运行时、默认训练或模型参数，不改设置即时/保存生效的既有语义。

## Capabilities

### New Capabilities
- `grouped-settings-navigation`: 设置分组、响应式导航、草稿与按需加载。

### Modified Capabilities
无。

## Impact

frontend/src/components/layout/Settings、common/Button 的复用、i18n/en.json 与 zh.json、frontend/dist、OpenSpec 和本地 docs/todo.md。无后端或依赖变更。
