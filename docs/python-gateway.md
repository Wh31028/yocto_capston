# Python Gateway

`python-legacy` 브랜치의 Python Gateway와 FastAPI dashboard 동작을 설명한다.

## 주요 파일

```text
meta-can-fota/recipes-apps/can-fota/files/can-fota-BBB/
├── web_dashboard/main.py
├── web_dashboard/templates/index.html
├── custom_lte_gateway.py
├── custom_lte_gateway_f103.py
├── isotp_lte_gateway.py
└── isotp_lte_gateway_f103.py
```

## Board / protocol 선택

```text
f407 + custom → custom_lte_gateway.py
f407 + isotp  → isotp_lte_gateway.py
f103 + custom → custom_lte_gateway_f103.py
f103 + isotp  → isotp_lte_gateway_f103.py
```

## Dashboard endpoint

`web_dashboard/main.py`에서 확인되는 endpoint:

- `GET /`: dashboard HTML
- `POST /upload`: 업로드 파일 저장
- `WebSocket /ws`: CAN frame 표시, FOTA 시작, 로그 및 진행률 전달

업로드 파일 저장 경로:

```text
/usr/share/can-fota/received_fw.bin
```

CAN sniffer는 Raw SocketCAN으로 `can0`에 연결하고, 최대 50개 frame을 200ms 단위로 dashboard에 전달한다.

## 직접 실행

```bash
python3 custom_lte_gateway.py /path/to/firmware.bin
python3 custom_lte_gateway_f103.py /path/to/firmware.bin
python3 isotp_lte_gateway.py /path/to/firmware.bin
python3 isotp_lte_gateway_f103.py /path/to/firmware.bin
```

Gateway 실행 과정:

1. `can0` down/up 및 bitrate 설정
2. Raw SocketCAN bind
3. `0x200 + DE AD` FOTA 진입 요청
4. START/DATA/END/JUMP 수행
5. 응답 및 진행률 출력

## Web service

`can-fota.service`는 다음 명령으로 dashboard를 실행한다.

```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

작업 경로:

```text
/usr/share/can-fota/web_dashboard
```
