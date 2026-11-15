FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY app ./app

EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://%s:%s/healthz'%(os.getenv('BRIDGE_HOST','127.0.0.1'),os.getenv('BRIDGE_PORT','8100')),timeout=3)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host ${BRIDGE_HOST:-127.0.0.1} --port ${BRIDGE_PORT:-8100} --no-access-log"]
