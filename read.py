import asyncio
from playwright.async_api import async_playwright
import json
import random
import re
from urllib.parse import urlparse, urlunparse
import logging
import traceback
from bs4 import BeautifulSoup
from wcwidth import wcswidth
from tqdm.asyncio import tqdm
from tqdm import tqdm as std_tqdm
import os


url_list = [
    {"name": "开发调优", "url": "https://linux.do/c/develop/4"},
    {"name": "资源荟萃", "url": "https://linux.do/c/resource/14"},
    {"name": "文档共建", "url": "https://linux.do/c/wiki/42"},
    {"name": "跳蚤市场", "url": "https://linux.do/c/trade/10"},
    {"name": "非我莫属", "url": "https://linux.do/c/job/27"},
    {"name": "读书成诗", "url": "https://linux.do/c/reading/32"},
    {"name": "前沿快讯", "url": "https://linux.do/c/news/34"},
    {"name": "福利羊毛", "url": "https://linux.do/c/welfare/36"},
    {"name": "搞七捻三", "url": "https://linux.do/c/gossip/11"},
    {"name": "运营反馈", "url": "https://linux.do/c/feedback/2"}
]

class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super(TqdmLoggingHandler, self).__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            std_tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

def preprocess_cookies(cookies):
    for cookie in cookies:
        if 'sameSite' in cookie:
            if cookie['sameSite'] == 'unspecified':
                cookie['sameSite'] = 'Lax'
            elif cookie['sameSite'] == 'lax':
                cookie['sameSite'] = 'Lax'
            elif cookie['sameSite'] == 'strict':
                cookie['sameSite'] = 'Strict'
            elif cookie['sameSite'] == 'none':
                cookie['sameSite'] = 'None'
        else:
            cookie['sameSite'] = 'Lax'
        cookie.pop('hostOnly', None)
        cookie.pop('session', None)
        cookie.pop('storeId', None)
        cookie.pop('id', None)
        if 'domain' not in cookie or 'name' not in cookie or 'value' not in cookie:
            raise ValueError(f"Invalid cookie: {cookie}")
    return cookies

def parse_user_info(h1_text):
    # 示例文本: "你好，ee (datehoer) 2级用户"
    pattern = r"你好，(.*?) \((.*?)\) (\d+)级用户"
    match = re.search(pattern, h1_text)
    if match:
        username = match.group(1)
        account = match.group(2)
        level = int(match.group(3))
        return username, account, level
    else:
        return None, None, None

def parse_table_data(div_html):
    soup = BeautifulSoup(div_html, 'html.parser')
    table = soup.find('table')
    data = []
    if table:
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all(['th', 'td'])
            cols_text = [col.get_text(strip=True) for col in cols]
            data.append(cols_text)
    return data

def print_table(table_data):
    # 计算每一列的最大宽度
    if not table_data:
        logging.info("未找到表格数据。")
        return
    cols_width = []
    for col in zip(*table_data):
        max_len = max(wcswidth(str(item)) for item in col)
        cols_width.append(max_len)
    # 打印表格
    for row in table_data:
        row_text = ''
        for i, item in enumerate(row):
            item_str = str(item)
            padding = cols_width[i] - wcswidth(item_str)
            row_text += item_str + ' ' * (padding + 2)
        logging.info(row_text)

async def collect_post_urls(page, max_scroll_count, visited_urls):
    previous_height = None
    scroll_count = 0
    collected_urls = set()
    while scroll_count <= max_scroll_count:
        # 收集帖子链接
        posts = await page.query_selector_all("xpath=/html/body/section/div[1]/div[3]/div[2]/div[4]/div[2]/div/div/div/table/tbody/tr/td[1]/span/a")
        for post in posts:
            post_url = await post.get_attribute('href')
            if not post_url.startswith('http'):
                post_url = 'https://linux.do' + post_url
            if post_url not in visited_urls:
                collected_urls.add(post_url)
        # 滚动页面
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(10, 30))
        # 检查是否到底部
        current_height = await page.evaluate("document.body.scrollHeight")
        if previous_height == current_height:
            break
        previous_height = current_height
        scroll_count += 1
    return list(collected_urls)

async def visit_unvisited_posts(page, post_urls, visited_urls, max_scroll_count, category_name, can_like_count, max_read_count):
    max_visit_count = min(max_read_count, len(post_urls))
    visited_count = 0
    unvisited_posts = list(set(post_urls) - set(visited_urls))
    random.shuffle(unvisited_posts)
    now_like_count = 0
    for _ in tqdm(range(max_visit_count), desc=f"访问 {category_name} 板块帖子", unit="帖子"):
        if not unvisited_posts:
            logging.info(f"{category_name} 板块下所有帖子已访问完毕")
            break
        
        post_url = unvisited_posts.pop()
        post_url = normalize_post_url(post_url)
        logging.info(f"正在访问 {category_name} 板块下未访问过的帖子：{post_url}")
        visited_urls.append(post_url)
        
        try:
            await page.goto(post_url)
            await asyncio.sleep(random.uniform(20, 40))
            await scroll_page(page, max_scroll_count)
            if now_like_count <= can_like_count:
                now_like_count += await like_post(page)
            await asyncio.sleep(random.uniform(20, 40))
        except Exception as e:
            logging.error(f"访问帖子 {post_url} 时发生错误: {str(e)}")
        
        visited_count += 1

    logging.info(f"在 {category_name} 板块共访问了 {visited_count} 个帖子")

async def scroll_page(page, max_scroll_count):
    previous_height = None
    scroll_count = 0
    while scroll_count <= max_scroll_count:
        await page.evaluate("window.scrollBy(0, 400)")
        await asyncio.sleep(random.uniform(5, 10))
        current_height = await page.evaluate("document.body.scrollHeight")
        if previous_height == current_height:
            break
        previous_height = current_height
        scroll_count += 1

async def like_post(page):
    like_buttons = await page.query_selector_all(".discourse-reactions-reaction-button:not(.has-reacted)")
    if like_buttons:
        num_likes = len(like_buttons)
        likes_to_give = max(1, min(10, int(num_likes * 0.1)))
        buttons_to_like = random.sample(like_buttons, likes_to_give)
        for button in buttons_to_like:
            try:
                await button.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(1, 2))
                await button.click(force=True)
                await asyncio.sleep(random.uniform(6, 15))
            except Exception as e:
                logging.info(f"点赞时发生错误：{e}")
        logging.info(f"点赞了 {likes_to_give} 个回复")
        return likes_to_give
    else:
        logging.info("没有找到可以点赞的按钮")
        return 0

        
async def login(page, username, password):
    login_button = ".login-button"
    await asyncio.sleep(random.uniform(2, 4))
    # 点击登录按钮打开登录弹窗
    await page.click(login_button)
    await asyncio.sleep(random.uniform(2, 4))
    # 填写用户名
    await page.fill("#login-account-name", username)
    await asyncio.sleep(random.uniform(1, 2))
    # 填写密码
    await page.fill("#login-account-password", password)
    await asyncio.sleep(random.uniform(1, 2))
    # 点击登录按钮
    await page.click("#login-button")
    await asyncio.sleep(random.uniform(5, 10))  # 等待登录完成
    # 检查是否登录成功
    login_button_after_login = await page.query_selector("#toggle-current-user .avatar")
    if login_button_after_login is not None:
        logging.info("登录成功")
        return True
    else:
        logging.error("登录失败，请检查用户名和密码。")
        return False

def normalize_post_url(post_url):
    """
    将帖子链接规范化，去掉末尾的斜杠和路径，使其格式为：https://linux.do/t/topic/219094
    """
    parsed_url = urlparse(post_url)
    path_parts = parsed_url.path.strip('/').split('/')
    if len(path_parts) >= 3:
        new_path = '/' + '/'.join(path_parts[:3])
        normalized_url = urlunparse((parsed_url.scheme, parsed_url.netloc, new_path, '', '', ''))
        return normalized_url
    else:
        return post_url

async def check_new_posts(page):
    xpath = "/html/body/section/div[1]/div[3]/div[2]/div[3]/div/section[2]/ul/li[2]/a"
    element = await page.query_selector(f'xpath={xpath}')
    if not element:
        logging.info("未找到新帖子的元素。")
        return 1, None
    text = await element.inner_text()
    match = re.search(r'新\s*\((\d+)\)', text)
    if match:
        new_count = int(match.group(1))
    else:
        new_count = 1
    return new_count

async def get_user_info(page):
    await page.goto('https://connect.linux.do/')
    await asyncio.sleep(random.uniform(2, 4))
    h1_text = await page.inner_text('xpath=/html/body/h1')
    username_parsed, account, level = parse_user_info(h1_text)
    logging.info(f"用户名: {username_parsed}, 账号: {account}, 等级: {level}")
    
    if level and level > 1:
        div_html = await page.inner_html('xpath=/html/body/div[3]')
        table_data = parse_table_data(div_html)
        print_table(table_data)
    else:
        logging.info("用户等级不大于1，无需解析表格数据。")
    
    return level

async def main():
    need_read_cookie = False
    visited_urls = []
    max_scroll_count = 5
    max_like_count = 50
    max_read_count = 10
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    if username is None or password is None:
        logging.error("未设置用户名或密码，请设置环境变量 USERNAME 和 PASSWORD。")
        return
    use_proxy = os.getenv("USE_PROXY", "False").lower() in ("true", "1", "t")
    proxy_address = os.getenv("PROXY_ADDRESS", "")
    async with async_playwright() as p:
        # 设置代理配置
        proxy = None
        if use_proxy:
            proxy = {
                "server": proxy_address,
            }
        browser = await p.chromium.launch(headless=True, proxy=proxy)
        context = await browser.new_context()
        if need_read_cookie:
            with open('cookies.json', 'r') as f:
                cookies = json.load(f)
            processed_cookies = preprocess_cookies(cookies)
            await context.add_cookies(processed_cookies)
        page = await context.new_page()
        await page.goto('https://linux.do')
        login_status = True
        if not need_read_cookie:
            login_status = await login(page, username, password)
        if login_status or need_read_cookie:
            try:
                level = await get_user_info(page)
                for category in tqdm(url_list, desc="访问板块"):
                    can_like_count = min(1, max_like_count // len(url_list))
                    category_name = category['name']
                    category_url = category['url']
                    await page.goto(category_url)
                    await asyncio.sleep(random.uniform(2, 4))
                    new_count = await check_new_posts(page)
                    logging.info(f"在 {category_name} 发现新帖子数量：{new_count}")
                    max_scroll_count = max(1, new_count // 10)
                    # 在类别页面滚动并收集帖子URL
                    post_urls = await collect_post_urls(page, max_scroll_count, visited_urls)
                    logging.info(f"在 {category_name} 收集到的帖子URL数量：{len(post_urls)}")
                    # 访问未访问过的帖子
                    await visit_unvisited_posts(page, post_urls, visited_urls, max_scroll_count, category_name, can_like_count, max_read_count)
                if level and level > 1:
                    await get_user_info(page)
            except KeyboardInterrupt:
                logging.info(f"用户手动停止脚本。{str(traceback.format_exc())}")
            except Exception as e:
                logging.error(f"发生错误：{str(e)}, {str(traceback.format_exc())}")
            finally:
                logging.info(f"访问过{len(visited_urls)}条帖子URL")
                await browser.close()
        else:
            logging.error("登录失败，检查用户名密码")
            await browser.close()
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        handlers=[TqdmLoggingHandler()],
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding='utf-8'
    )
    asyncio.run(main())