# 标准提示片段库

## 项目风格

列出已接受的 `style_core`，说明它只控制制作形态、材料、色彩、光影与画面密度，不接管身份、地理和剧情状态。

## 资产身份

按 `asset_id` 展示 `identity_full` 与 `continuity_lock`，文字必须逐字对应结构模型。

## 变体与视图

按 `variant_id` / `view_id` 展示 `variant_delta` 和 `view_projection`。

## 排除项

按资产展示 `negative_lock`；不得否定该资产的必需识别事实。

每条 Markdown 展示项必须同时显示 `fragment_id`、语言、适用范围、输入哈希和 `fragment_hash`。JSONL 是权威，Markdown 只是可再生视图。
