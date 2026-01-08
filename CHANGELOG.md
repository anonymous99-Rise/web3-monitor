# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/) 版本规范。

## [1.0.0] - 2026-01-08

### 新增
- 核心监控功能
  - BlockBeats 快讯采集 (预测市场、链上侦探、融资)
  - TechFlow 7x24h 快讯采集 (6 个分类 + 精选模式)
  - RootData 数据采集 (Top 100、透明度榜、交易所排名)
  - RootData 日历事件采集
  - RootData 未来 7 天加密日历洞察图片采集
  - RootData Market 数据概览图片采集
- Discord Webhook 推送
  - 富媒体 Embed 消息格式
  - Base64 图片转换与附件上传
- 数据存储
  - JSON 增量记录 (防止重复推送)
  - SQLite 持久化 (支持统计分析)
  - 分类图片存储 (`calendar_insights/`, `market_summary/`)
- 认证支持
  - Cookie 加载机制
  - 多站点独立认证配置
- GitHub Actions 工作流
  - 定时运行 (每小时)
  - 自动提交更新到仓库

### 文档
- README.md 使用说明
- docs/CONFIGURATION.md 配置指南
- CHANGELOG.md 更新日志
