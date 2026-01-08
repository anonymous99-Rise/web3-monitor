# 配置指南

本文档详细说明 `config.yaml` 的各项配置参数及获取方法。

## Discord 配置

```yaml
discord:
  webhook_url: "YOUR_DISCORD_WEBHOOK_URL"
  username: "Web3 Monitor"
  avatar_url: ""
```

| 字段 | 说明 | 必填 |
|------|------|------|
| `webhook_url` | Discord Webhook 链接 | ✅ |
| `username` | 机器人显示名称 | ❌ |
| `avatar_url` | 机器人头像 URL | ❌ |

### 获取 Webhook URL

1. 打开 Discord，进入目标服务器
2. 频道设置 → 整合 → Webhooks → 新建 Webhook
3. 复制 Webhook URL

---

## 站点配置

### BlockBeats

```yaml
blockbeats:
  enabled: true
  categories:
    - name: "预测市场"
      type: 1
    - name: "链上侦探"
      type: 2
    - name: "融资"
      type: 3
```

| type 值 | 分类名称 |
|---------|----------|
| 1 | 预测市场 |
| 2 | 链上侦探 |
| 3 | 融资 |

### TechFlow

```yaml
techflow:
  enabled: true
  is_hot: true  # 只采集精选
  categories:
    - name: "AI前沿"
      id: 1005
    - name: "加密股票"
      id: 1004
    - name: "项目动态"
      id: 1003
    - name: "市场观点"
      id: 1002
    - name: "链上数据"
      id: 1001
    - name: "融资动态"
      id: 1000
```

### RootData

```yaml
rootdata:
  enabled: true
  list_tasks:
    - name: "Top 100 项目"
      url: "https://cn.rootdata.com/rootdatalist/2025/top-projects"
  calendar:
    enabled: true
    insight_enabled: true  # 未来7天洞察图片
  market:
    enabled: true
```

---

## 认证配置 (登录态)

> **注意**: 大部分内容无需登录即可访问。仅在需要完整数据时配置。

```yaml
auth:
  blockbeats:
    enabled: false
    cookies: "token=xxx; user_id=xxx"

  techflow:
    enabled: false
    cookies: "tf_token=xxx"

  rootdata:
    enabled: false
    cookies: "token=xxx"
    api_token: ""  # 可选，用于 API 调用
```

### Cookie 获取方法

#### 方法一：开发者工具

1. 打开浏览器 (推荐 Chrome)，登录目标网站
2. 按 `F12` 打开开发者工具
3. 切换到 **Application** 选项卡
4. 左侧找到 **Storage → Cookies** → 选择对应域名
5. 复制所需 Cookie 值

#### 方法二：控制台导出

1. 按 `F12` → **Console**
2. 输入: `document.cookie`
3. 复制完整输出字符串

### 各站点关键 Cookie

| 站点 | Cookie 名称 | 说明 |
|------|-------------|------|
| BlockBeats | `token` | 用户令牌 |
| BlockBeats | `user_id` | 用户 ID |
| TechFlow | `tf_token` | 会话令牌 |
| RootData | `token` | 页面认证 Cookie |

---

## RootData API 配置 (推荐)

RootData 提供官方 API，比页面采集更稳定。使用 API 需要申请 Access Key。

### 获取 API Key

1. 登录 [RootData](https://cn.rootdata.com/)
2. 访问 [API 文档页面](https://cn.rootdata.com/Api/Doc)
3. 复制您的 **Access Key**

### 配置示例

```yaml
auth:
  rootdata:
    enabled: true
    cookies: ""  # 可选，用于页面采集
    api_key: "RJughDKWvQAIPs61dFaMn3vhP5jNUP4A"  # 您的 API Key
```

### API 调用方式

API 通过 HTTP Header 传递认证信息：

```bash
curl -X POST \
  -H "apikey: YOUR_API_KEY" \
  -H "language: zh" \
  -H "Content-Type: application/json" \
  -d '{"days": 1}' \
  https://api.rootdata.com/open/hot_index
```

### 常用 API 端点

| 端点 | 说明 | Credits |
|------|------|---------|
| `/open/hot_index` | Top 100 热门项目 | 10/次 |
| `/open/get_fac` | 融资轮次信息 | 2/条 |
| `/open/ser_inv` | 搜索项目/机构 | 免费 |
| `/open/quotacredits` | 查询余额 | 免费 |

> **注意**: Basic 版本每月 1000 Credits，请合理规划调用频率。


### 图片存储结构

```
downloads/
├── calendar_insights/    # 日历洞察图片
│   └── 未来7天加密日历洞察_2026-01-08.png
└── market_summary/       # 市场数据图片
    └── Top Gainers_2026-01-08.png
```
