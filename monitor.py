import os
import time
import json
import yaml
import base64
import requests
import asyncio
import sqlite3
import logging
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

# 日志配置
def setup_logging():
    """配置双日志系统：run.log 和 err.log"""
    # 创建 logs 目录
    if not os.path.exists("./logs"):
        os.makedirs("./logs")
    
    # 运行日志
    run_handler = logging.FileHandler("./logs/run.log", encoding="utf-8")
    run_handler.setLevel(logging.INFO)
    run_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    
    # 错误日志
    err_handler = logging.FileHandler("./logs/err.log", encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s\n%(exc_info)s"))
    
    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    
    # 配置 logger
    logger = logging.getLogger("web3_monitor")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(run_handler)
    logger.addHandler(err_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()


class Config:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f)
        
        # Override with env vars if present
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", self.data["discord"]["webhook_url"])
        self.history_file = self.data["settings"].get("history_file", "processed_ids.json")
        self.image_dir = self.data["settings"].get("image_dir", "./downloads")
        
        # Discord 开关
        self.discord_enabled = self.data["discord"].get("enabled", True)
        
        # Markdown 存储目录
        self.markdown_dir = self.data["settings"].get("markdown_dir", "./output")
        
        # 页脚配置
        self.footer_text = self.data["discord"].get("footer", "Power By 东方隐侠安全团队·Anonymous@ 隐侠安全客栈")
        
        # RootData API Key (优先从环境变量读取)
        rootdata_auth = self.data.get("auth", {}).get("rootdata", {})
        self.rootdata_api_key = os.getenv("ROOTDATA_API_KEY", rootdata_auth.get("api_key", ""))
        
        # 创建必要的目录
        for dir_path in [self.image_dir, self.markdown_dir]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)



class DiscordPusher:
    def __init__(self, webhook_url, footer_text="Power By 东方隐侠安全团队·Anonymous@ 隐侠安全客栈"):
        self.webhook_url = webhook_url
        self.footer_text = footer_text
        self.enabled = True

    def send_embed(self, title, description, url=None, image_path=None, color=0x00ff00, timestamp=None, fields=None, max_retries=3):
        if not self.enabled:
            logger.info(f"Discord 推送已禁用，跳过: {title}")
            return
        
        # 添加页脚
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        footer = {
            "text": f"{self.footer_text} • {now}"
        }
        
        embed = {
            "title": title,
            "description": description,
            "url": url,
            "color": color,
            "footer": footer,
            "timestamp": timestamp or datetime.utcnow().isoformat()
        }
        
        # 添加字段
        if fields:
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        
        files = None
        file_handles = []
        if image_path and os.path.exists(image_path):
            filename = os.path.basename(image_path)
            payload["embeds"][0]["image"] = {"url": f"attachment://{filename}"}
            fh = open(image_path, "rb")
            file_handles.append(fh)
            files = {filename: fh}
        
        # 重试机制
        for attempt in range(max_retries):
            try:
                resp = requests.post(self.webhook_url, json=payload if not files else None, 
                                     data={"payload_json": json.dumps(payload)} if files else None,
                                     files=files)
                
                # 处理 429 Rate Limit
                if resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 5)
                    logger.warning(f"Discord 429 限流，等待 {retry_after}s 后重试 (尝试 {attempt+1}/{max_retries})")
                    time.sleep(retry_after + 0.5)
                    # 重置文件指针
                    for fh in file_handles:
                        fh.seek(0)
                    continue
                
                resp.raise_for_status()
                logger.info(f"推送成功: {title}")
                break

            except Exception as e:
                logger.error(f"Discord 推送失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                    for fh in file_handles:
                        fh.seek(0)
        
        # 关闭文件
        for fh in file_handles:
            fh.close()


    def send_startup_notification(self, version="1.0.0", sites_enabled=None):
        """发送启动通知"""
        now = datetime.now()
        start_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 监控类型
        monitor_types = []
        if sites_enabled:
            if sites_enabled.get("blockbeats"): monitor_types.append("BlockBeats")
            if sites_enabled.get("techflow"): monitor_types.append("TechFlow")
            if sites_enabled.get("rootdata"): monitor_types.append("RootData")
        
        fields = [
            {"name": "启动时间", "value": start_time, "inline": True},
            {"name": "服务状态", "value": "✅ 已启动", "inline": True},
            {"name": "版本信息", "value": f"V{version}", "inline": True},
            {"name": "监控类型", "value": ", ".join(monitor_types) or "无", "inline": True},
            {"name": "推送渠道", "value": "Discord Webhook", "inline": True},
            {"name": "运行模式", "value": "单次执行" if True else "持续运行", "inline": True}
        ]
        
        self.send_embed(
            title="🚀 Web3-Monitor 已启动!",
            description=f"**启动时间**: {start_time}",
            color=0x5865F2,  # Discord 蓝
            fields=fields
        )

    def send_news_embed(self, source, category, title, content, url, publish_time):
        """发送新闻推送 - 格式化版本"""
        # 颜色映射
        color_map = {
            "blockbeats": 0x3498db,  # 蓝色
            "techflow": 0xe74c3c,     # 红色
            "rootdata": 0xf39c12     # 橙色
        }
        
        # 截断内容
        content_text = content[:450] + "..." if len(content) > 450 else content
        
        # 构建 description（包含链接）
        desc_parts = [content_text]
        if url:
            desc_parts.append(f"\n\n🔗 **链接**: [查看原文]({url})")
        
        fields = [
            {"name": "📂 分类", "value": category or "未分类", "inline": True},
            {"name": "⏰ 时间", "value": publish_time or datetime.now().strftime("%H:%M"), "inline": True}
        ]
        
        self.send_embed(
            title=f"【{source.upper()} - {category}】{title}",
            description="\n".join(desc_parts),
            url=url,
            color=color_map.get(source.lower(), 0x00ff00),
            fields=fields
        )


    def send_table_embed(self, title, rows, source="rootdata", table_url=None, page_size=5):
        """发送表格数据推送 - 分页显示"""
        if not rows:
            return
        
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        total = len(rows)
        
        # 分页处理
        for page_num, start_idx in enumerate(range(0, min(total, 10), page_size)):
            end_idx = min(start_idx + page_size, total, 10)
            page_rows = rows[start_idx:end_idx]
            
            # 清理和格式化每行数据
            formatted_rows = []
            for i, row in enumerate(page_rows, start_idx + 1):
                # 移除多余空白，按制表符或多空格分割
                cells = [c.strip() for c in row.replace("\n", " ").split("\t") if c.strip()]
                if not cells:
                    cells = [c.strip() for c in row.split("  ") if c.strip()]
                
                if len(cells) >= 2:
                    name = cells[0][:15]
                    info = " | ".join(cells[1:3]) if len(cells) > 1 else ""
                    formatted_rows.append(f"`{i:2}.` **{name}** {info[:40]}")
                else:
                    formatted_rows.append(f"`{i:2}.` {row[:50]}")
            
            page_title = f"{title}" if page_num == 0 else f"{title} (续)"
            description = f"**今日榜单 {start_idx+1}-{end_idx}:**\n\n" + "\n".join(formatted_rows)
            
            fields = [
                {"name": "📅 更新时间", "value": now, "inline": True},
                {"name": "📊 数据来源", "value": source.upper(), "inline": True},
                {"name": "🔗 查看完整", "value": f"[点击查看]({table_url})" if table_url else "无", "inline": True}
            ]
            
            self.send_embed(
                title=page_title,
                description=description,
                url=table_url,
                color=0xf39c12,
                fields=fields
            )
            
            # 避免触发 Rate Limit
            if page_num < (min(total, 10) - 1) // page_size:
                time.sleep(1)



    def send_base64_image(self, title, description, base64_str, filename="image.png", url=None, subfolder="general"):

        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        
        image_data = base64.b64decode(base64_str)
        # 优雅的文件夹结构: downloads/{subfolder}/filename
        folder_path = os.path.join("./downloads", subfolder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        full_path = os.path.join(folder_path, filename)
        with open(full_path, "wb") as f:
            f.write(image_data)
        
        logger.info(f"    Image saved to: {full_path}")
        self.send_embed(title, description, url=url, image_path=full_path)

    def send_file_image(self, title, description, file_path, url=None):
        """发送本地文件图片到 Discord"""
        if not os.path.exists(file_path):
            logger.warning(f"    Image file not found: {file_path}")
            return
        
        logger.info(f"    Sending image file: {file_path}")
        self.send_embed(title, description, url=url, image_path=file_path)


class Web3Monitor:
    def __init__(self, config):
        self.config = config
        self.pusher = DiscordPusher(config.webhook_url, config.footer_text)
        self.pusher.enabled = config.discord_enabled
        self.history = self.load_history()
        self.db = self.init_database()
        
        # 初始化 Markdown 存储目录
        self.md_dirs = {
            "blockbeats": os.path.join(config.markdown_dir, "blockbeats"),
            "techflow": os.path.join(config.markdown_dir, "techflow"),
            "rootdata": os.path.join(config.markdown_dir, "rootdata")
        }
        for path in self.md_dirs.values():
            if not os.path.exists(path):
                os.makedirs(path)

    def save_to_markdown(self, source, category, title, content, url="", publish_time=""):
        """保存采集结果到 Markdown 文件"""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
        # 文件路径
        md_dir = self.md_dirs.get(source, self.config.markdown_dir)
        filename = f"{date_str}.md"
        filepath = os.path.join(md_dir, filename)
        
        # Markdown 内容
        md_content = f"""
---

## 📰 {title}

> **分类**: {category}  
> **时间**: {publish_time or time_str}  
> **来源**: [{source}]({url})

{content}

---
*{self.config.footer_text} • {now.strftime("%Y/%m/%d %H:%M")}*

"""
        
        # 追加写入
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(md_content)
        
        logger.info(f"已保存到 Markdown: {filepath}")


    def init_database(self):
        """初始化 SQLite 数据库"""
        db_path = self.config.data["settings"].get("database", "data.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 创建新闻表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                category TEXT,
                title TEXT NOT NULL,
                content TEXT,
                url TEXT,
                publish_time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建图片表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                type TEXT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        print(f"  Database initialized: {db_path}")
        return conn

    def save_news(self, source, category, title, content="", url="", publish_time=""):
        """保存新闻到数据库"""
        cursor = self.db.cursor()
        cursor.execute('''
            INSERT INTO news (source, category, title, content, url, publish_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (source, category, title, content, url, publish_time))
        self.db.commit()

    def save_image_record(self, source, img_type, filename, filepath):
        """保存图片记录到数据库"""
        cursor = self.db.cursor()
        cursor.execute('''
            INSERT INTO images (source, type, filename, filepath)
            VALUES (?, ?, ?, ?)
        ''', (source, img_type, filename, filepath))
        self.db.commit()

    def load_history(self):
        if os.path.exists(self.config.history_file):
            with open(self.config.history_file, "r") as f:
                return set(json.load(f))
        return set()

    def save_history(self):
        with open(self.config.history_file, "w") as f:
            json.dump(list(self.history), f)

    async def check_login_status(self, page, site):
        """检测登录状态，如果失效则发送提醒"""
        # 常见的登录提示选择器
        login_selectors = [
            ".login-required",
            ".please-login",
            ".need-login",
            "text='请登录'",
            "text='请先登录'",
            "text='Login Required'"
        ]
        
        for selector in login_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    print(f"  ⚠️ {site} 登录状态可能已失效")
                    self.pusher.send_embed(
                        title=f"⚠️ {site} 登录状态失效",
                        description="Cookie 可能已过期，请更新后重新运行。\n\n获取方法：F12 → Application → Cookies",
                        color=0xff0000
                    )
                    return False
            except:
                pass
        return True

    async def scrape_blockbeats(self, browser):

        print("Scraping BlockBeats...")
        page = await browser.new_page()
        bb_conf = self.config.data["sites"]["blockbeats"]
        for cat in bb_conf["categories"]:
            url = f"https://www.theblockbeats.info/newsflash?type={cat['type']}"
            print(f"  Category: {cat['name']} - {url}")
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except:
                # 如果 networkidle 超时，尝试 domcontentloaded
                await page.goto(url, wait_until="domcontentloaded")
            
            # 等待一下让 JS 渲染
            await asyncio.sleep(2)
            
            # 检测登录状态
            if not await self.check_login_status(page, "BlockBeats"):
                continue
            
            try:
                # 尝试多个可能的选择器
                await page.wait_for_selector(".news-flash-item, .news-flash-wrapper, [class*='flash']", timeout=10000)
            except Exception as e:
                print(f"    Failed to load items: {e}")
                continue
            
            # 尝试获取新闻列表
            items = await page.query_selector_all(".news-flash-item")
            if not items:
                items = await page.query_selector_all(".news-flash-wrapper")
            if not items:
                items = await page.query_selector_all("[class*='news-flash']")

            for item in items:
                title_el = await item.query_selector(".news-flash-title-text")
                content_el = await item.query_selector(".news-flash-item-content p")
                time_el = await item.query_selector(".news-flash-title")
                link_el = await item.query_selector("a:has-text('原文链接')")
                
                if not title_el: continue

                
                title = (await title_el.inner_text()).strip()
                content = (await content_el.inner_text()).strip() if content_el else ""
                item_time = (await time_el.inner_text()).strip().split('\n')[0] if time_el else ""
                link = await link_el.get_attribute("href") if link_el else ""
                
                item_id = f"bb_{cat['type']}_{title}_{item_time}"
                if item_id not in self.history:
                    logger.info(f"  [BlockBeats] 新快讯: {title}")
                    full_url = link if link.startswith("http") else f"https://www.theblockbeats.info{link}"
                    
                    # 推送到 Discord (使用格式化方法)
                    self.pusher.send_news_embed(
                        source="BlockBeats",
                        category=cat['name'],
                        title=title,
                        content=content,
                        url=full_url,
                        publish_time=item_time
                    )
                    
                    # 保存到 Markdown
                    self.save_to_markdown("blockbeats", cat['name'], title, content, full_url, item_time)
                    
                    # 保存到数据库
                    self.save_news("blockbeats", cat['name'], title, content, full_url, item_time)
                    self.history.add(item_id)

        await page.close()



    async def scrape_techflow(self, browser):
        print("Scraping TechFlow...")
        page = await browser.new_page()
        tf_conf = self.config.data["sites"]["techflow"]
        is_hot = tf_conf.get("is_hot", False)
        
        for cat in tf_conf["categories"]:
            url = f"https://www.techflowpost.com/zh-CN/newsletter?articleType={cat['id']}"
            if is_hot:
                url += "&is_hot=1"
            
            logger.info(f"  Category: {cat['name']} - {url}")
            await page.goto(url)
            
            # 检测登录状态
            if not await self.check_login_status(page, "TechFlow"):
                continue
            
            try:
                await page.wait_for_selector("a[href*='/newsletter/']", timeout=10000)
            except:
                continue
            
            # 获取年份（页面顶部显示）
            current_year = datetime.now().strftime("%Y")
            
            # 获取新闻项目容器（包含时间信息）
            news_containers = await page.query_selector_all("div.flex.flex-col.gap-5 > div")
            
            for item_container in news_containers[:10]:
                try:
                    # 获取时间（格式如 "1/8 08:27"）
                    time_el = await item_container.query_selector("span[class*='text-[10px]']")
                    if not time_el:
                        time_el = await item_container.query_selector("[class*='text-gray']")
                    
                    item_time = ""
                    if time_el:
                        time_text = (await time_el.inner_text()).strip()
                        # 转换格式 "1/8 08:27" -> "2026/01/08 08:27"
                        if "/" in time_text and " " in time_text:
                            parts = time_text.split(" ")
                            if len(parts) >= 2:
                                date_part = parts[0].split("/")
                                if len(date_part) == 2:
                                    month = date_part[0].zfill(2)
                                    day = date_part[1].zfill(2)
                                    item_time = f"{current_year}/{month}/{day} {parts[1]}"
                    
                    # 获取链接和标题
                    link_el = await item_container.query_selector("a[href*='/newsletter/']")
                    if not link_el:
                        continue
                    
                    link = await link_el.get_attribute("href")
                    texts = await link_el.inner_text()
                    lines = [line.strip() for line in texts.split('\n') if line.strip()]
                    if not lines:
                        continue
                    
                    title = lines[0]
                    content = "\n".join(lines[1:])
                    
                    # 提取原始链接
                    orig_link_el = await item_container.query_selector("a.inline-block")
                    orig_link = await orig_link_el.get_attribute("href") if orig_link_el else ""

                    item_id = f"tf_{cat['id']}_{link}"
                    if item_id not in self.history:
                        logger.info(f"  [TechFlow] 新快讯: {title}")
                        full_url = orig_link or f"https://www.techflowpost.com{link}"
                        
                        # 推送到 Discord (使用格式化方法)
                        self.pusher.send_news_embed(
                            source="TechFlow",
                            category=cat['name'],
                            title=title,
                            content=content,
                            url=full_url,
                            publish_time=item_time
                        )
                        
                        # 保存到 Markdown
                        self.save_to_markdown("techflow", cat['name'], title, content, full_url, item_time)
                        
                        # 保存到数据库
                        self.save_news("techflow", cat['name'], title, content, full_url, item_time)
                        self.history.add(item_id)
                except Exception as e:
                    logger.warning(f"  TechFlow item parse error: {e}")
                    continue

        await page.close()




    async def scrape_rootdata(self, browser):
        logger.info("Scraping RootData...")
        page = await browser.new_page()
        rd_conf = self.config.data["sites"]["rootdata"]
        
        # 1. 列表任务 (Top 100, 透明度等)
        for task in rd_conf["list_tasks"]:
            logger.info(f"  List: {task['name']}")
            await page.goto(task['url'])
            
            # 检测登录状态
            if not await self.check_login_status(page, "RootData"):
                continue
            
            try:
                await page.wait_for_selector("table tr, .list-item", timeout=15000)
                # 这里我们只推送前10名
                rows = await page.query_selector_all("table tr")

                data_summary = []
                for row in rows[1:11]: # 前10
                    text = await row.inner_text()
                    data_summary.append(text.strip())
                
                item_id = f"rd_list_{task['name']}_{datetime.now().strftime('%Y%m%d')}"
                if item_id not in self.history and data_summary:
                    logger.info(f"  [RootData] 新榜单: {task['name']}")
                    # 使用表格推送方法
                    self.pusher.send_table_embed(
                        title=f"【RootData - {task['name']}】",
                        rows=data_summary,
                        source="rootdata",
                        table_url=task['url']
                    )
                    # 保存到 Markdown
                    self.save_to_markdown("rootdata", task['name'], task['name'], 
                                         "\n".join([f"{i+1}. {r}" for i, r in enumerate(data_summary)]),
                                         task['url'], datetime.now().strftime("%Y/%m/%d %H:%M"))
                    self.history.add(item_id)
            except Exception as e:
                logger.error(f"  Failed to scrape list {task['name']}: {e}")

        # 2. 日历事件 (今日)
        if rd_conf["calendar"]["enabled"]:
            logger.info("  Calendar Events...")
            await page.goto(rd_conf["calendar"]["url"])

            try:
                # 使用正确的列表选择器
                await page.wait_for_selector(".list-table, .list-row", timeout=15000)
                # 提取今日事件（从列表行）
                events = await page.evaluate('''() => {
                    const rows = document.querySelectorAll('.list-row');
                    return Array.from(rows).slice(0, 10).map(row => {
                        // 尝试提取项目名和事件描述
                        const project = row.querySelector('a[href*="/Projects/detail/"]')?.innerText.trim() || "";
                        const desc = row.innerText.replace(project, "").replace(/\\n/g, " ").trim();
                        return project ? `${project} | ${desc}` : row.innerText.replace(/\\n/g, " | ").trim();
                    });
                }''')
                if events and len(events) > 0:
                    event_str = "\n".join([f"{i+1}. {e}" for i, e in enumerate(events)])
                    item_id = f"rd_cal_events_{datetime.now().strftime('%Y%m%d')}"
                    if item_id not in self.history:
                        logger.info(f"  [RootData] 日历事件: {len(events)} 条")
                        self.pusher.send_embed(
                            title="📅 RootData | 今日日历事件",
                            description=f"**最新事件:**\n{event_str[:1800]}",
                            url=rd_conf["calendar"]["url"],
                            color=0x2ecc71,
                            fields=[
                                {"name": "📊 事件数量", "value": str(len(events)), "inline": True},
                                {"name": "📅 日期", "value": datetime.now().strftime("%Y/%m/%d"), "inline": True}
                            ]
                        )
                        # 保存到 Markdown
                        self.save_to_markdown("rootdata", "日历事件", "今日日历事件", event_str, 
                                            rd_conf["calendar"]["url"], datetime.now().strftime("%Y/%m/%d %H:%M"))
                        self.history.add(item_id)
            except Exception as e:
                logger.warning(f"  Calendar events fetch failed: {e}")

            # 3. 未来7天洞察图片
            if rd_conf["calendar"].get("insight_enabled"):
                logger.info("  Calendar Insight Image...")
                try:
                    # 点击橙色分享图标 (class: img-btn 或 day-perfix)
                    icon = await page.query_selector(".img-btn, .day-perfix img, div.create-banner-btn")
                    if icon:
                        await icon.click()
                        logger.info("    Clicked calendar insight icon")
                        # 等待弹窗出现
                        await page.wait_for_selector(".v-dialog, .calendar-img, .ant-modal-content, .el-dialog", timeout=10000)
                        
                        # 点击 "生成分享图" 按钮 (如果存在)
                        gen_btn = await page.query_selector("button:has-text('生成分享图'), button:has-text('Generate'), .generate-btn")
                        if gen_btn:
                            await gen_btn.click()
                            logger.info("    Clicked generate share image button")
                            
                        await asyncio.sleep(4)  # 等待 Canvas 渲染
                        
                        # 点击下载按钮 (通常是中间的按钮，第二个 .img-btn)
                        # 优先尝试 src 包含 download 的图片，或者第二个 img-btn
                        download_btn = await page.query_selector("img[src*='download'], div.img-btn:nth-child(2) img, .img-btn:nth-of-type(2) img")
                        if download_btn:
                            date_str = datetime.now().strftime('%Y-%m-%d')
                            filename = f"未来7天加密日历洞察_{date_str}.png"
                            save_path = os.path.join(self.config.output_dir, "rootdata", "calendar_insights", filename)
                            os.makedirs(os.path.dirname(save_path), exist_ok=True)
                            
                            # 使用 expect_download 捕获下载
                            async with page.expect_download(timeout=30000) as download_info:
                                await download_btn.click()
                                logger.info("    Clicked download button")
                            
                            download = await download_info.value
                            await download.save_as(save_path)
                            logger.info(f"    Saved Calendar Image: {save_path}")
                            
                            # 推送到 Discord（使用文件方式）
                            self.pusher.send_file_image(
                                "📅 RootData | 未来7天加密日历洞察",
                                f"采集数据自 RootData 日历 ({date_str})",
                                save_path
                            )
                            
                            # 保存记录到数据库
                            self.save_image_record("rootdata", "calendar_insight", filename, save_path)
                        else:
                            logger.warning("    Download button not found")
                    else:
                        logger.warning("    Calendar insight icon not found")
                except Exception as e:
                    logger.warning(f"    Insight capture failed: {e}")



        # 4. Market 图片
        if rd_conf["market"]["enabled"]:
            logger.info("  Market Image...")
            await page.goto(rd_conf['market']['url'])
            try:
                await page.wait_for_selector(".v-data-table, table, .top-gainers", timeout=10000)
                
                # 点击下载图标（通过 src 包含 download 定位）
                dl_icon = await page.query_selector("img[src*='download'], .header-gainers img, .down-icon")
                if dl_icon:
                    await dl_icon.click()
                    logger.info("    Clicked market download icon")
                    await asyncio.sleep(3)
                    
                    # 等待预览弹窗出现
                    await page.wait_for_selector(".v-dialog, .el-dialog, .generate-img-footer", timeout=10000)
                    await asyncio.sleep(2)
                    
                    # 点击"保存"按钮
                    save_btn = await page.query_selector("button.action_btn, .v-btn:has-text('保存'), button:has-text('保存')")

                    if save_btn:
                        date_str = datetime.now().strftime('%Y-%m-%d')
                        filename = f"Market_Top_Gainers_{date_str}.png"
                        save_path = os.path.join(self.config.output_dir, "rootdata", "market_summary", filename)
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        
                        # 使用 expect_download 捕获下载
                        async with page.expect_download(timeout=30000) as download_info:
                            await save_btn.click()
                            logger.info("    Clicked save button")
                        
                        download = await download_info.value
                        await download.save_as(save_path)
                        logger.info(f"    Saved Market Image: {save_path}")
                        
                        # 推送到 Discord（使用文件方式）
                        self.pusher.send_file_image(
                            "📊 RootData | Top Gainers",
                            f"市场概览数据 ({date_str})",
                            save_path
                        )
                        
                        # 保存记录到数据库
                        self.save_image_record("rootdata", "market_summary", filename, save_path)
                    else:
                        logger.warning("    Save button not found")
                else:
                    logger.warning("    Market download icon not found")
            except Exception as e:
                logger.warning(f"    Market capture failed: {e}")


        
        await page.close()



    def parse_cookies(self, cookie_str, domain):
        """将 Cookie 字符串解析为 Playwright 格式"""
        cookies = []
        if not cookie_str:
            return cookies
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                name, value = item.split("=", 1)
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": domain,
                    "path": "/"
                })
        return cookies

    async def run(self, once=False):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config.data["settings"]["headless"])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # 加载认证 Cookie
            auth_conf = self.config.data.get("auth", {})
            all_cookies = []
            
            # BlockBeats Cookie
            bb_auth = auth_conf.get("blockbeats", {})
            if bb_auth.get("enabled") and bb_auth.get("cookies"):
                all_cookies.extend(self.parse_cookies(bb_auth["cookies"], ".theblockbeats.info"))
                print("  Loaded BlockBeats cookies")
            
            # TechFlow Cookie
            tf_auth = auth_conf.get("techflow", {})
            if tf_auth.get("enabled") and tf_auth.get("cookies"):
                all_cookies.extend(self.parse_cookies(tf_auth["cookies"], ".techflowpost.com"))
                print("  Loaded TechFlow cookies")
            
            # RootData Cookie
            rd_auth = auth_conf.get("rootdata", {})
            if rd_auth.get("enabled") and rd_auth.get("cookies"):
                all_cookies.extend(self.parse_cookies(rd_auth["cookies"], ".rootdata.com"))
                print("  Loaded RootData cookies")
            
            if all_cookies:
                await context.add_cookies(all_cookies)
                logger.info(f"  Total {len(all_cookies)} cookies loaded")
            
            # 发送启动通知
            sites_enabled = {
                "blockbeats": self.config.data["sites"]["blockbeats"]["enabled"],
                "techflow": self.config.data["sites"]["techflow"]["enabled"],
                "rootdata": self.config.data["sites"]["rootdata"]["enabled"]
            }
            self.pusher.send_startup_notification(version="1.0.0", sites_enabled=sites_enabled)
            
            while True:
                try:
                    if self.config.data["sites"]["blockbeats"]["enabled"]:
                        await self.scrape_blockbeats(context)
                    if self.config.data["sites"]["techflow"]["enabled"]:
                        await self.scrape_techflow(context)
                    if self.config.data["sites"]["rootdata"]["enabled"]:
                        await self.scrape_rootdata(context)
                    
                    self.save_history()
                    logger.info(f"Cycle completed. {datetime.now()}")
                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}")
                
                if once: break
                await asyncio.sleep(self.config.data["sites"].get("global_interval", 300))



if __name__ == "__main__":
    import sys
    config = Config()
    monitor = Web3Monitor(config)
    
    once = "--once" in sys.argv
    asyncio.run(monitor.run(once=once))
