# 프론트엔드 빌드 → 파이썬 런타임 하나에 정적 서빙까지 합쳐서, Render에 서비스 하나만
# 올리면 되게 만든다(CORS·두 서비스 관리 안 해도 됨).
#
# 2026-08-04: 데모 영상(LastSight_Demo.mp4, 211MB)은 처음엔 이 이미지 안에 받아와 백엔드가
# 직접 스트리밍했는데, Render 무료 티어(RAM 512MB·CPU 0.1코어)에서 웹소켓 실시간 갱신과
# 동시에 돌리니 간헐적으로 503이 나는 게 실측으로 확인됐다 — 서버가 큰 파일을 스트리밍할
# 여력이 부족했던 것. 프론트엔드가 GitHub Release 에셋 URL로 직접 요청하도록 바꿔서
# (frontend/src/api.ts의 DEMO_VIDEO_URL) Render 서버가 영상을 아예 안 거치게 했다 —
# 그래서 이 이미지에는 더 이상 영상을 받아올 필요가 없다.

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
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /frontend/dist ./frontend/dist

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
