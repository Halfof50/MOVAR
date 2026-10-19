# MOVAR V7 FastAPI 시작하기

다운로드한 ZIP 파일을 VS Code에서 프로젝트 루트(`/home/yong/projects/movar-ai`)로 옮긴 뒤 풀어주세요.
이 패키지는 `api/main.py`, `api/__init__.py`, `requirements-api.txt`만 추가하며 학습 파일이나 체크포인트를 수정하지 않습니다.

```bash
cd /home/yong/projects/movar-ai
unzip movar_api_starter.zip
python3 -m pip install -r requirements-api.txt
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

프로젝트에는 다음 기존 파일이 있어야 합니다.
- `src/models/movar_eupe.py`
- `scripts/finetune_eupe_v7_512.py`
- `third_party/EUPE/`
- `weights/eupe/EUPE-ViT-S.pt`
- `outputs/checkpoints/eupe_finetune_512_ratio_mild_v7/best.pt`

서버가 시작되면 `http://127.0.0.1:8000/docs`에서 `/predict` -> `Try it out` -> 이미지 선택 -> `Execute` 하세요.

```bash
curl -X POST "http://127.0.0.1:8000/predict" -F "file=@/path/to/photo.jpg"
```

- `GET /health`: 모델 로딩 상태 확인
- `POST /predict`: 사진 1장 업로드 -> 6개 증상의 0~3등급, 등급별 softmax 점수 반환
- **Test split을 사용하지 않음**: V7 `best.pt`을 로딩한 뒤 추론만 실행
- V7 Validation과 **동일한** `make_transform(train=False)` 사용 (512 비율유지 + 검은 여백 + ImageNet 정규화)
- 업로드 파일을 디스크에 저장하지 않음
- 실험용 로컬 서버이므로 인터넷에 바로 공개하지 마세요. 외부 공개 시 인증/HTTPS/요청 제한 등이 필요합니다.
- 사용자 두피 사진을 의료 진단으로 표현하지 마세요.

환경변수 선택 사항:
`MOVAR_CHECKPOINT` (다른 체크포인트 경로), `MOVAR_CORS_ORIGINS` (프런트엔드 허용 출처 목록)

예: `MOVAR_CORS_ORIGINS=http://localhost:5173,http://localhost:3000 python3 -m uvicorn api.main:app --port 8000`
