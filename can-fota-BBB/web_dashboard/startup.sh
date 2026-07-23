#!/bin/bash
# =====================================================
# BeagleBone Black FOTA Dashboard 자동 시작 스크립트
# (구: start_lte_fota.sh + fota_listener.py 대체)
# =====================================================

echo "========================================="
echo " BeagleBone Black FOTA Gateway 시작 중..."
echo "========================================="

# 1. LTE 모뎀(eth3)이 인식될 때까지 15초 대기
echo "[Boot] LTE 모뎀 초기화 대기 중... (15초)"
sleep 15

# 2. LTE 인터넷 라우팅 강제 설정
echo "[Boot] LTE 라우팅 설정 중..."
ip route replace default via 192.168.8.1 dev eth3
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "[Boot] LTE 라우팅 완료."

# 3. CAN 핀 하드웨어 설정 (P9.24=CAN TX, P9.26=CAN RX)
echo "[Boot] CAN 핀 설정 중..."
config-pin P9.24 can
config-pin P9.26 can
echo "[Boot] CAN 핀 설정 완료."

# 4. CAN 인터페이스 활성화 (1Mbps)
echo "[Boot] CAN 인터페이스 활성화 중..."
ip link set can0 down 2>/dev/null
ip link set can0 up type can bitrate 1000000 2>/dev/null
echo "[Boot] CAN0 활성화 완료."

# 5. BoneScript 중지 (8000번 포트 확보)
echo "[Boot] Stopping BoneScript..."
systemctl stop bonescript.socket bonescript.service 2>/dev/null

# 6. FastAPI 웹 대시보드 서버 시작 (백그라운드 실행)
echo "[Boot] FOTA 웹 대시보드 서버 시작 중..."
cd /home/debian/web_dashboard
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &

# 7. ngrok 터널 시작
sleep 5
echo "[Boot] Starting ngrok tunnel..."
pkill -f ngrok 2>/dev/null
sleep 1
ngrok http 8000
