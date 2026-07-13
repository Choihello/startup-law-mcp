FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUTF8=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY law_search.py law_sync.py program_sync.py programs.py stages.py \
     server.py server_http.py ./
COPY data/ data/

# 인덱스를 이미지에 구움 — 런타임 빌드 불필요, 콜드스타트 최소화
RUN python law_search.py build

EXPOSE 8080
CMD ["python", "server_http.py"]
