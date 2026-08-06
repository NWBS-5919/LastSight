# frontend

React + Vite + TypeScript 대시보드. 웹소켓으로 백엔드(`app/ws/live.py`)와 실시간 연동해 데모 시나리오(평상시 → 화재감지 → 경보 → 2차 확인 → 구조 브리핑 챗봇)를 재생하는 단일 페이지 앱. 화면 구성 상세는 `docs/screen_guide.md` 참고.

## 실행

```bash
npm install
npm run dev
```

`http://localhost:5173`에서 뜬다. 개발 모드에서는 API_BASE가 자동으로 `http://localhost:8000`을 가리키므로(`src/api.ts`) 백엔드를 8000번 포트에 먼저 띄워둘 것 — `../backend/README.md` 참고. 배포(Render 등, 백엔드가 이 빌드 결과물을 같은 오리진에서 서빙)에서는 상대 경로를 그대로 쓰므로 별도 설정이 필요 없다.

```bash
npm run build   # tsc -b && vite build — 타입 에러가 있으면 빌드 자체가 실패한다
npm run preview # 빌드 결과물을 로컬에서 확인
```

**타입체크만 따로 하려면** `npx tsc -p tsconfig.app.json --noEmit`을 쓸 것 — 루트 `tsconfig.json`은 references만 있는 파일이라 `npx tsc --noEmit`은 아무것도 검사하지 않는다.

## 폴더 역할

- `src/App.tsx` — 페이지 전체. 화재경보 유무로 테마·통계 카드 구성을 자동 전환하고, 나머지는 모달로 여닫는 구조(별도 라우팅 없음)
- `src/api.ts` — 백엔드 REST/웹소켓 호출 전부. `DEMO_VIDEO_URL`은 Render 서버를 거치지 않고 GitHub Release URL을 직접 가리킨다
- `src/types.ts` — `backend/app/models/schemas.py`와 동기화 유지해야 하는 응답 타입 정의
- `src/hooks/useLiveState.ts` — 웹소켓 연결 + 최초 스냅샷 fetch를 감싼 훅. 화면 대부분이 이 훅 하나의 상태를 그대로 씀
- `src/components/DashboardTimeline.tsx` — 평상시 PPE 이력 + 화재 발생 + 2차 확인을 잇는 통합 타임라인(가장 복잡한 컴포넌트). 라벨 다단 배치는 `src/timelineLayout.ts`
- `src/components/DetectionOverlay.tsx` — 영상 위에 SVG로 박스를 그리는 공용 오버레이(평상시 착용/미착용 라벨, 비상시 초록 박스, 화재 박스 전부 여기서 처리)
- `src/components/PpeViolationCard.tsx`/`PpeViolationEditModal.tsx` — PPE 위반 카드 + 관리자 정정(안전모/안전조끼 착용·미착용) 모달
- `src/components/SituationCard.tsx`/`SituationDetailModal.tsx` — 2차 확인 카드 + 상세(프레임+카테고리별 박스) 모달
- `src/components/ZoneMapModal.tsx` — 구역 보기/그리기·이름 편집 모달
- `src/components/FireAlertModal.tsx`/`SituationChatPanel.tsx` — 화재 발생 상세 모달, 영상 옆 Gemini 구조 브리핑 챗봇 패널
- `src/situationUtils.ts` — 2차 확인 카테고리 색상·집계 헬퍼(`STAY_CATEGORY` 등 — 코드의 상태값 이름은 `CLAUDE.md` 4번과 동기화 유지)

## 안전/개인정보 원칙 (프론트엔드에서 특히 지킬 것)

- 로그·카드를 사람 ID로 그룹핑하거나 "동일인 추정"을 자동으로 표시하지 않는다 — 관리자가 사진을 보고 직접 판단하게 한다
- "대피 완료"·"전원 안전" 같은 확정 문구를 UI 어디에도 쓰지 않는다. 2차 확인·구조 브리핑 챗봇 결과는 항상 "추정 정보 — 확정 아님" disclaimer와 함께 보여준다
- 자세한 내용은 프로젝트 루트 `CLAUDE.md` 2번(절대 원칙) 참고
