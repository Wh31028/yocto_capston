# CAN FOTA Gateway

BeagleBone Black에서 STM32 Target ECU로 firmware를 전송하는 Python 기반 CAN-FOTA Gateway입니다.

현재 문서는 `python-legacy` 브랜치 기준입니다.

## 구성

```text
BeagleBone Black
├── FastAPI Web Dashboard
├── Python Custom Gateway
├── Python ISO-TP Gateway
└── SocketCAN can0
        ↓
STM32 Target ECU
```

지원 대상:

- STM32F407
- STM32F103RB
- Custom FOTA
- ISO-TP FOTA

## 빠른 실행

```bash
python3 custom_lte_gateway_f103.py firmware.bin
python3 isotp_lte_gateway_f103.py firmware.bin
```

Dashboard:

```text
http://<BBB-IP>:8000
```

서비스 상태:

```bash
systemctl status setup-can0.service
systemctl status can-fota.service
```

## 기본 설정

```text
CAN interface: can0
FOTA entry ID: 0x200
Entry payload: DE AD
F103 bitrate: 500kbps
```

현재 F407용 Python Gateway와 dashboard 기본 bitrate는 1Mbps이며, F103용 Gateway와 `setup-can0.service`는 500kbps를 사용합니다.

## Branch

```text
python-legacy
└── 기존 Python Gateway 구현

main
└── C flasher 기반 최신 구현으로 전환 예정
```

## 상세 문서

- [Python Gateway](docs/python-gateway.md)
- [FOTA Protocol](docs/fota-protocol.md)
- [Yocto Build and Deployment](docs/yocto-build.md)
- [Legacy Status and Limitations](docs/legacy-status.md)
