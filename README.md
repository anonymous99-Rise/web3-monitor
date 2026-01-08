# Web3 Monitor

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Playwright-Latest-green.svg" alt="Playwright">
  <img src="https://img.shields.io/badge/Discord-Webhook-7289da.svg" alt="Discord">
</p>

一个基于 Playwright 的 Web3 资讯监控工具，自动采集 BlockBeats、TechFlow、RootData 的最新数据，并以 Embed 形式推送至 Discord。

## ✨ 功能特性

- **BlockBeats 快讯监控**: 分类采集预测市场、链上侦探、融资等频道
- **TechFlow 7x24h 快讯**: 支持 6 个分类，默认精选模式
- **RootData 深度采集**:
  - Top 100 项目排行榜
  - 透明度评分榜
  - 交易所透明度排名
  - 日历事件汇总
  - 未来 7 天加密日历洞察 (图片)
  - Market 数据概览 (图片)
- **Discord 推送**: 富媒体 Embed + 图片附件
- **SQLite 持久化**: 支持历史数据统计分析
- **GitHub Actions**: 自动化部署运行

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-repo/web3_monitor.git
cd web3_monitor
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. 配置

编辑 `config.yaml`，填入您的 Discord Webhook URL：

```yaml
discord:
  webhook_url: "YOUR_DISCORD_WEBHOOK_URL"
```

详细配置说明请参考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

### 4. 运行

```bash
# 持续运行
python monitor.py

# 单次测试
python monitor.py --once
```

## 📁 项目结构

```
web3_monitor/
├── monitor.py              # 主程序
├── config.yaml             # 配置文件
├── requirements.txt        # Python 依赖
├── data.db                 # SQLite 数据库
├── processed_ids.json      # 已推送记录
├── downloads/              # 图片存储
│   ├── calendar_insights/  # 日历洞察图片
│   └── market_summary/     # 市场数据图片
├── docs/
│   └── CONFIGURATION.md    # 配置说明
└── .github/workflows/
    └── monitor.yml         # GitHub Actions
```

## ☁️ GitHub Actions 部署

1. Fork 本仓库
2. 在仓库 **Settings → Secrets → Actions** 添加:
   - `DISCORD_WEBHOOK_URL`: 您的 Discord Webhook 链接
3. 工作流将每小时自动运行

## 📊 数据持久化

采集的数据会存储到 SQLite 数据库 (`data.db`)，支持后续分析：

```sql
-- 查询今日推送数量
SELECT source, COUNT(*) FROM news WHERE date(created_at) = date('now') GROUP BY source;

-- 查询热门项目
SELECT title, COUNT(*) as mentions FROM news GROUP BY title ORDER BY mentions DESC LIMIT 10;
```

## 📝 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解版本历史。

## 📄 许可证

MIT License
