# ==============================================================================
# BeagleBone Black CAN-FOTA 애플리케이션 및 서비스 설치 BitBake 레시피
# ==============================================================================
SUMMARY = "BeagleBone Black CAN-FOTA Gateway and FastAPI Dashboard"
DESCRIPTION = "Python SocketCAN based CAN-FOTA Gateway application with FastAPI Web Dashboard"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# ------------------------------------------------------------------------------
# 소스 파일 및 시스템 서비스 파일 지정
# file:// 구문은 레시피 디렉터리 하위의 files/ 폴더 내 파일이나 지정 디렉터리를 가져옴
# ------------------------------------------------------------------------------
SRC_URI = " \
    file://can-fota-BBB \
    file://setup-can0.service \
    file://can-fota.service \
"

# 가져온 파일들이 위치할 빌드 임시 작업 경로 (${WORKDIR})
S = "${WORKDIR}"

# ------------------------------------------------------------------------------
# systemd 클래스 상속
# Yocto 이미지 생성 시 systemd 서비스 등록 및 자동 시작 링크 생성을 보장함
# ------------------------------------------------------------------------------
inherit systemd

SYSTEMD_PACKAGES = "${PN}"
SYSTEMD_SERVICE:${PN} = "setup-can0.service can-fota.service"
# 타겟 이미지 설치 시 부팅 자동 시작 활성화
SYSTEMD_AUTO_ENABLE:${PN} = "enable"


# ------------------------------------------------------------------------------
# 런타임 의존성 (RDEPENDS)
# BeagleBone Black 타겟 리눅스에 함께 설치되어야 하는 파이썬 라이브러리 및 유틸리티
# ------------------------------------------------------------------------------
RDEPENDS:${PN} += " \
    python3 \
    python3-core \
    python3-asyncio \
    python3-websockets \
    python3-jinja2 \
    python3-fastapi \
    python3-uvicorn \
    can-utils \
    iproute2 \
    bash \
"

# ------------------------------------------------------------------------------
# 설치 태스크 (do_install)
# 빌드 디렉터리에 있는 파일들을 타겟 이미지 내부의 실제 리눅스 디렉터리 구조(${D})로 복사
# ------------------------------------------------------------------------------
do_install() {
    # 1. 파이썬 앱 및 웹 대시보드 소스 설치 (/usr/share/can-fota)
    # ${datadir} 변수는 리눅스 표준 경로인 /usr/share 를 의미함
    install -d ${D}${datadir}/can-fota
    cp -r ${S}/can-fota-BBB/* ${D}${datadir}/can-fota/

    # 2. systemd 서비스 파일 설치 (/lib/systemd/system)
    # ${systemd_system_unitdir} 변수는 /lib/systemd/system 경로를 의미함
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${S}/setup-can0.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${S}/can-fota.service ${D}${systemd_system_unitdir}/
}

# ------------------------------------------------------------------------------
# 최종 패키지 파일 묶음 명시
# do_install에서 복사된 경로들을 패키지에 포함하도록 패키징 시스템에 지정
# ------------------------------------------------------------------------------
FILES:${PN} += " \
    ${datadir}/can-fota \
    ${systemd_system_unitdir}/setup-can0.service \
    ${systemd_system_unitdir}/can-fota.service \
"
