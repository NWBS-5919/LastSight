# 프론트엔드 빌드 → 파이썬 런타임 하나에 정적 서빙까지 합쳐서, Render에 서비스 하나만
# 올리면 되게 만든다(CORS·두 서비스 관리 안 해도 됨). 데모 영상(LastSight_Demo.mp4)은
# 용량이 커서(200MB+) git에 안 올리고 GitHub Release 에셋으로만 관리 — 빌드 시점에
# 여기서 받아온다(docs: 배포 전 README/개발 로그 참고).

FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

# opencv-python-headless가 일부 배포판에서 libGL/libglib를 필요로 함(정적 이미지
# 인코딩/디코딩만 쓰지만, 휠이 이 공유 라이브러리들을 찾는 경우가 있어 방어적으로 설치).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /frontend/dist ./frontend/dist

# 데모 영상을 GitHub Release에서 받아온다 — release_asset_url은 빌드 인자로 넘겨
# 다른 Release로 교체하더라도 Dockerfile을 다시 안 고쳐도 되게 한다.
ARG DEMO_VIDEO_URL=https://github.com/NWBS-5919/LastSight/releases/download/demo-assets-v1/LastSight_Demo.mp4
RUN curl -fL "$DEMO_VIDEO_URL" -o LastSight_Demo.mp4

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
