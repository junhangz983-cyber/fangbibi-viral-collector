# MediaCrawler 对接说明

## 外部依赖

- 仓库只引用外部 `MediaCrawler`
- 不把它的源码、运行目录、浏览器缓存、登录态一起提交

## 已知字段来源

- 抖音：`title` / `desc` / `create_time` / `nickname` / `liked_count` / `collected_count` / `comment_count` / `share_count` / `aweme_url`
- 小红书：`title` / `desc` / `time` / `nickname` / `liked_count` / `collected_count` / `comment_count` / `share_count` / `note_url`

## 校准点

- `liked_count` 是主筛选条件
- `collected_count` 对小红书更有意义
- `aweme_url` 和 `note_url` 优先作为去重键

