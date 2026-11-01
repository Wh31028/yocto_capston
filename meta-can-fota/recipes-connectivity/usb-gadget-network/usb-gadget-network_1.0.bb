# ==============================================================================
# USB NCM gadget networking for development access (SSH over USB)
#   BBB: 192.168.7.2/24 on usb0, DHCP server hands out 192.168.7.100-119
# ==============================================================================
SUMMARY = "USB NCM Ethernet gadget network configuration for BeagleBone Black"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://g_ncm.conf \
    file://10-usb0.network \
"

S = "${WORKDIR}"

do_install() {
    install -d ${D}${sysconfdir}/modules-load.d
    install -m 0644 ${WORKDIR}/g_ncm.conf ${D}${sysconfdir}/modules-load.d/

    install -d ${D}${sysconfdir}/systemd/network
    install -m 0644 ${WORKDIR}/10-usb0.network ${D}${sysconfdir}/systemd/network/
}

FILES:${PN} = " \
    ${sysconfdir}/modules-load.d/g_ncm.conf \
    ${sysconfdir}/systemd/network/10-usb0.network \
"

RDEPENDS:${PN} = "kernel-module-g-ncm"
