---
name: fangbibi-viral-collector
description: 方比比爆款采集与对标入库 Skill。用于按关键词或对标账号采集抖音/小红书爆款，过滤高赞内容，去重后整理成飞书多维表格。触发于“给我按关键词找爆款”“扒对标账号”“同步到飞书 Base”“做爆款语料库/灵感库/对标账号表”这类任务。
---

# Fangbibi Viral Collector

## 目标

把“关键词采集”和“对标账号采集”收成同一条流水线，最后只落一张飞书对比账号表。

## 输入

- 关键词列表
- 对标账号列表或账号主页链接
- 平台：默认先抖音，再补小红书
- 最低爆款门槛：默认 `5000` 赞

## 输出

只写入这一张表，字段固定为：
- 标题
- 链接
- 平台
- 账号
- 发布时间
- 点赞
- 收藏
- 评论
- 分享
- 开头钩子
- 爆点判断

## 工作流

1. 先确认是“关键词”还是“对标账号”。
2. 用 `MediaCrawler` 跑抖音优先，XHS 作为补充。
3. 只保留点赞数达到门槛的内容。
4. 去重，优先保留链接唯一的一条。
5. 用 `scripts/normalize_records.py` 统一字段。
6. 写入飞书多维表格；没有写表权限时先导出 CSV。

## 采集规则

- 不复制 `MediaCrawler` 源码到本仓库。
- 不保存 Cookie、登录态、飞书 token、浏览器缓存、原始采集大包。
- 抖音和小红书都可以跑，但 XHS 的登录态和风控更不稳定，失败时先回到抖音。
- 记录只认公开可见内容；不要把评论楼层、无关噪声和重复结果写进表。
- `爆点判断` 先给结论，再由人工二次修正，别把它装成绝对真理。

## 参考

- `references/collection-flow.md`
- `references/feishu-base-schema.md`
- `references/media-crawler-notes.md`
- `scripts/normalize_records.py`
