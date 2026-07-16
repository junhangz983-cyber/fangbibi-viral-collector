# 每日爆款监测

## 当前架构

```text
第三方采集软件导出的 Excel/CSV
        ↓
import_social_media_export.py（门槛过滤、链接去重）
        ↓
飞书多维表格 + 飞书私聊推送
```

浏览器和 `MediaCrawler` 都不是日常主通道。只有第三方导出无法提供数据、且 Chrome 已登录抖音时，才使用 `daily_douyin_monitor.py` 临时补采。

## 手动运行

```bash
python3 scripts/import_social_media_export.py \
  --input "/path/to/视频数据.xlsx" \
  --base-token "$FANGBIBI_FEISHU_BASE_TOKEN" \
  --table-id "$FANGBIBI_FEISHU_TABLE_ID" \
  --min-likes 20000
```

先加 `--dry-run` 核验数量；确认后再正式写入。Chrome 只在临时补采时需要打开并保持抖音登录。

## 数据边界

- 只写点赞数至少 `20000` 的公开视频。
- 以视频链接为唯一去重键。
- 每条新记录写入 `入库日期` 和 `搜索关键词`；同一链接的多词命中会合并为 `关键词 A｜关键词 B`。
- 导出不提供标题、文案或开头钩子时，必须写 `待补标题`，不能推测内容。
- 原始导出不会进入 Git 仓库。
- 私聊推送只从实际写入的新增数据生成前 10 条。

## 定时运行

用户要求定时任务时，用 Codex App automation 创建或更新任务；任务前提是第三方采集软件已将最新导出放到约定目录。浏览器兜底才依赖 Chrome 启动和抖音登录态。
