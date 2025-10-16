# 基于官方 Python 镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY requirements.txt .
COPY *.py ./

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量（也可在运行时通过-e覆盖）
ENV MCP_ENDPOINT=""
ENV MUSIC_API_KEY=""

# 启动命令（默认运行计算器服务）
CMD ["python", "mcp_pipe.py", "calculator.py"]
