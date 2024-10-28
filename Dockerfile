# 使用官方 Python 3.9 镜像作为基础镜像
FROM python:3.9-slim

# 设置环境变量，防止 Python 生成 .pyc 文件，并设置输出缓冲
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 更新包列表并安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    curl \
    wget \
    gnupg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 安装 Playwright 及其浏览器
RUN pip install --upgrade pip
RUN pip install playwright

# 安装 Playwright 所需的浏览器
RUN playwright install --with-deps

# 复制项目文件到容器中
WORKDIR /app
COPY . /app

# 手动安装所需的库
RUN pip install \
    asyncio \
    bs4 \
    wcwidth \
    tqdm

# 设置容器启动时执行的命令
CMD ["python", "read.py"]

