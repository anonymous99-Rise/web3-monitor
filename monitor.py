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

    def send_embed(self, title, description, url=None, image_path=None, color=0x00ff00, timestamp=None):
        if not self.enabled:
            logger.info(f"Discord 推送已禁用，跳过: {title}")
            return
        
        # 添加页脚
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        footer = {
            "text": f"{self.footer_text} • {now}"
        }
        
        payload = {
            "embeds": [{
                "title": title,
                "description": description,
                "url": url,
                "color": color,
                "footer": footer,
                "timestamp": timestamp or datetime.utcnow().isoformat()
            }]
        }
        
        files = None
        if image_path and os.path.exists(image_path):
            filename = os.path.basename(image_path)
            payload["embeds"][0]["image"] = {"url": f"attachment://{filename}"}
            files = {filename: open(image_path, "rb")}
        
        try:
            resp = requests.post(self.webhook_url, json=payload if not files else None, 
                                 data={"payload_json": json.dumps(payload)} if files else None,
                                 files=files)
            resp.raise_for_status()
            logger.info(f"推送成功: {title}")

        except Exception as e:
            print(f"Error sending to Discord: {e}")
        finally:
            if files:
                for f in files.values():
                    f.close()

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
        
        print(f"    Image saved to: {full_path}")
        self.send_embed(title, description, url=url, image_path=full_path)

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
                    
                    # 推送到 Discord
                    self.pusher.send_embed(
                        title=f"【BlockBeats - {cat['name']}】{title}",
                        description=f"{content}\n\n时间: {item_time}",
                        url=full_url,
                        color=0x3498db
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
            
            print(f"  Category: {cat['name']} - {url}")
            await page.goto(url)
            
            # 检测登录状态
            if not await self.check_login_status(page, "TechFlow"):
                continue
            
            try:
                await page.wait_for_selector("a[href*='/newsletter/']", timeout=10000)
            except:
                continue
                
            items = await page.query_selector_all("a[href*='/newsletter/']")

            for item in items[:10]: # 只看前10条
                # 尝试获取标题和内容
                texts = await item.inner_text()
                lines = [line.strip() for line in texts.split('\n') if line.strip()]
                if not lines: continue
                
                title = lines[0]
                content = "\n".join(lines[1:])
                link = await item.get_attribute("href")
                
                # 提取原始链接
                orig_link_el = await item.query_selector("a.inline-block")
                orig_link = await orig_link_el.get_attribute("href") if orig_link_el else ""

                item_id = f"tf_{cat['id']}_{link}"
                if item_id not in self.history:
                    logger.info(f"  [TechFlow] 新快讯: {title}")
                    full_url = orig_link or f"https://www.techflowpost.com{link}"
                    
                    # 推送到 Discord
                    self.pusher.send_embed(
                        title=f"【TechFlow - {cat['name']}】{title}",
                        description=f"{content}\n\n[查看详情](https://www.techflowpost.com{link})",
                        url=full_url,
                        color=0xe74c3c
                    )
                    
                    # 保存到 Markdown
                    self.save_to_markdown("techflow", cat['name'], title, content, full_url, "")
                    
                    # 保存到数据库
                    self.save_news("techflow", cat['name'], title, content, full_url, "")
                    self.history.add(item_id)
        await page.close()



    async def scrape_rootdata(self, browser):
        print("Scraping RootData...")
        page = await browser.new_page()
        rd_conf = self.config.data["sites"]["rootdata"]
        
        # 1. 列表任务 (Top 100, 透明度等)
        for task in rd_conf["list_tasks"]:
            print(f"  List: {task['name']}")
            await page.goto(task['url'])
            
            # 检测登录状态
            if not await self.check_login_status(page, "RootData"):
                continue
            
            try:
                await page.wait_for_selector("table tr, .list-item", timeout=15000)
                # 这里我们只推送前5名或者变动
                rows = await page.query_selector_all("table tr")

                data_summary = []
                for row in rows[1:11]: # 前10
                    text = await row.inner_text()
                    data_summary.append(text.replace("\t", " ").replace("\n", " ").strip())
                
                summary_str = "\n".join(data_summary)
                item_id = f"rd_list_{task['name']}_{datetime.now().strftime('%Y%m%d')}"
                if item_id not in self.history:
                    self.pusher.send_embed(
                        title=f"【RootData - {task['name']}】",
                        description=f"今日榜单前10：\n```\n{summary_str[:1800]}\n```",
                        url=task['url'],
                        color=0xf39c12
                    )
                    self.history.add(item_id)
            except Exception as e:
                print(f"    Failed to scrape list {task['name']}: {e}")

        # 2. 日历事件 (今日)
        if rd_conf["calendar"]["enabled"]:
            print("  Calendar Events...")
            await page.goto(rd_conf["calendar"]["url"])
            try:
                await page.wait_for_selector(".event-list, table", timeout=10000)
                # 提取今日事件
                events = await page.evaluate('''() => {
                    const items = document.querySelectorAll('.event-item, tr');
                    return Array.from(items).slice(0, 10).map(i => i.innerText.replace(/\\n/g, ' '));
                }''')
                if events:
                    event_str = "\n".join(events)
                    item_id = f"rd_cal_events_{datetime.now().strftime('%Y%m%d_%H')}"
                    if item_id not in self.history:
                        self.pusher.send_embed(
                            title="RootData | 今日日历事件",
                            description=f"最新事件：\n{event_str[:1800]}",
                            url=rd_conf["calendar"]["url"],
                            color=0x2ecc71
                        )
                        self.history.add(item_id)
            except: pass

            # 3. 未来7天洞察图片
            if rd_conf["calendar"].get("insight_enabled"):
                print("  Calendar Insight Image...")
                try:
                    # 尝试点击图标
                    icon = await page.query_selector("h1 + span img, .title + img, .calendar-insight-btn")
                    if icon:
                        await icon.click()
                        await asyncio.sleep(3)
                        gen_btn = await page.query_selector("text='生成分享图', .generate-btn")
                        if gen_btn:
                            await gen_btn.click()
                            await asyncio.sleep(5)
                            img_src = await page.evaluate('''() => {
                                const img = document.querySelector('.calendar-img img, .share-img img');
                                return img ? img.src : null;
                            }''')
                            if img_src and img_src.startswith("data:image"):
                                date_str = datetime.now().strftime('%Y-%m-%d')
                                filename = f"未来7天加密日历洞察_{date_str}.png"
                                print(f"    Captured Calendar Image: {filename}")
                                self.pusher.send_base64_image(
                                    "RootData | 未来7天加密日历洞察",
                                    f"采集数据自 RootData 日历 ({date_str})",
                                    img_src,
                                    filename=filename,
                                    subfolder="calendar_insights"
                                )
                except Exception as e:
                    print(f"    Insight capture failed: {e}")

        # 4. Market 图片
        if rd_conf["market"]["enabled"]:
            print("  Market Image...")
            await page.goto(rd_conf['market']['url'])
            try:
                # 点击下载图标
                dl_icon = await page.query_selector(".title:has-text('Top Gainers') + div img, .download-icon")
                if dl_icon:
                    await dl_icon.click()
                    await asyncio.sleep(3)
                    img_src = await page.evaluate('''() => {
                        const img = document.querySelector('.el-dialog img, .preview-img img');
                        return img ? img.src : null;
                    }''')
                    if img_src and img_src.startswith("data:image"):
                        title_text = await page.evaluate('''() => {
                            const titleEl = document.querySelector('.el-dialog__title, .modal-title');
                            return titleEl ? titleEl.innerText.trim() : "Market数据概览";
                        }''')
                        date_str = datetime.now().strftime('%Y-%m-%d')
                        # 移除非法文件名字符
                        clean_title = "".join([c for c in title_text if c.isalnum() or c in (' ', '_', '-')]).strip()
                        filename = f"{clean_title}_{date_str}.png"
                        self.pusher.send_base64_image(
                            f"RootData | {title_text}",
                            f"市场概览数据 ({date_str})",
                            img_src,
                            filename=filename,
                            subfolder="market_summary"
                        )
            except Exception as e:
                print(f"    Market capture failed: {e}")
        
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
                print(f"  Total {len(all_cookies)} cookies loaded")
            
            while True:
                try:
                    if self.config.data["sites"]["blockbeats"]["enabled"]:
                        await self.scrape_blockbeats(context)
                    if self.config.data["sites"]["techflow"]["enabled"]:
                        await self.scrape_techflow(context)
                    if self.config.data["sites"]["rootdata"]["enabled"]:
                        await self.scrape_rootdata(context)
                    
                    self.save_history()
                    print(f"Cycle completed. {datetime.now()}")
                except Exception as e:
                    print(f"Error in monitor loop: {e}")
                
                if once: break
                await asyncio.sleep(self.config.data["sites"].get("global_interval", 300))


if __name__ == "__main__":
    import sys
    config = Config()
    monitor = Web3Monitor(config)
    
    once = "--once" in sys.argv
    asyncio.run(monitor.run(once=once))
