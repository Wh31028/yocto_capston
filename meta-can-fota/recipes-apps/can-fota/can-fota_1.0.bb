# ==============================================================================
# BeagleBone Black CAN-FOTA FastAPI 애플리케이션 및 자동 서비스 레시피
# ==============================================================================
SUMMARY = "CAN-FOTA FastAPI Web Dashboard and Services for BeagleBone Black"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# ------------------------------------------------------------------------------
# 소스 파일 지정
# ------------------------------------------------------------------------------
SRC_URI = " \
    file://can-fota-BBB \
    file://setup-can0.service \
    file://can-fota.service \
    file://ngrok-fota.service \
    file://ngrok.yml \
"

S = "${WORKDIR}"

inherit systemd

SYSTEMD_PACKAGES = "${PN}"
SYSTEMD_SERVICE:${PN} = "setup-can0.service can-fota.service ngrok-fota.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

# ------------------------------------------------------------------------------
# 런타임 의존성 (RDEPENDS)
# ------------------------------------------------------------------------------
RDEPENDS:${PN} += " \
    python3 \
    python3-core \
    python3-asyncio \
    python3-websockets \
    python3-jinja2 \
    python3-fastapi \
    python3-uvicorn \
    python3-annotated-types \
    python3-python-multipart \
    can-utils \
    iproute2 \
    bash \
    ngrok \
"

# ------------------------------------------------------------------------------
# 설치 태스크 (do_install)
# ------------------------------------------------------------------------------
do_install() {
    # 1. 파이썬 앱 및 웹 대시보드 소스 설치 (/usr/share/can-fota)
    install -d ${D}${datadir}/can-fota
    cp -r ${S}/can-fota-BBB/* ${D}${datadir}/can-fota/

    # 2. systemd 서비스 파일 설치 (/lib/systemd/system)
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${S}/setup-can0.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${S}/can-fota.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${S}/ngrok-fota.service ${D}${systemd_system_unitdir}/

    # 3. ngrok 토큰 설정 파일 설치 (/etc/ngrok.yml)
    install -d ${D}${sysconfdir}
    install -m 0644 ${S}/ngrok.yml ${D}${sysconfdir}/ngrok.yml
}

# ------------------------------------------------------------------------------
# 최종 패키지 파일 묶음 명시
# ------------------------------------------------------------------------------
FILES:${PN} += " \
    ${datadir}/can-fota \
    ${systemd_system_unitdir}/setup-can0.service \
    ${systemd_system_unitdir}/can-fota.service \
    ${systemd_system_unitdir}/ngrok-fota.service \
    ${sysconfdir}/ngrok.yml \
"
