# ==============================================================================
# BBeagleBone Black 커널 CAN 드라이버 모듈 및 DTS 핀맵 자동 패치 bbappend
# ==============================================================================
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI:append = " \
    file://can.cfg \
    file://0001-am335x-boneblack-add-can0.patch \
"
