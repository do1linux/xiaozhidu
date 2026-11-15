FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY xiaoai_bot.py .

# 小米登录 token 落在这里，务必挂卷，否则每次重建都要重新验证码登录
VOLUME ["/root"]

CMD ["python", "xiaoai_bot.py"]
