# Python Legacy Status

## 보존 대상

이 branch에는 C SocketCAN flasher로 전환하기 전의 다음 구현이 보존되어 있다.

- F407 Custom Python Gateway
- F407 ISO-TP Python Gateway
- F103 Custom Python Gateway
- F103 ISO-TP Python Gateway
- FastAPI Web dashboard
- CAN frame WebSocket monitor
- LTE firmware download 경로
- ngrok systemd service
- Yocto package 및 CAN0 자동 설정

## 확인되지 않은 기능

- C SocketCAN flasher
- FreeRTOS Application
- Linux heartbeat platform driver
- `/dev/fota_status`
- GPIO heartbeat IRQ 처리
- Yocto kernel module recipe
- 자동화된 FOTA fault test

## 현재 제한사항

- Dashboard 기본 bitrate는 1Mbps다.
- F407용 Python Gateway는 1Mbps를 설정한다.
- F103용 Python Gateway와 `setup-can0.service`는 500kbps를 설정한다.
- 실제 Target CAN bitrate와 Gateway 설정이 일치해야 한다.
- Python Gateway의 실제 보드 FOTA 성공 여부는 repository만으로 확정할 수 없다.
- `ngrok.yml`에 실제 token을 넣어 commit하면 secret이 노출될 수 있다.

## Branch 관계

```text
python-legacy
└── 기존 Python Gateway 구현

main
└── C flasher 기반 최신 구현으로 전환 예정

feature/c-flasher-migration
└── Python Gateway를 C SocketCAN flasher로 교체한 개발 이력
```
