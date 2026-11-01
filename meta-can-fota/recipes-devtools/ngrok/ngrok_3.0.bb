SUMMARY = "ngrok - reverse proxy for secure tunnels"
HOMEPAGE = "https://ngrok.com"
LICENSE = "CLOSED"

SRC_URI = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz;downloadfilename=ngrok-v3-stable-linux-arm.tgz"
SRC_URI[sha256sum] = "7c8ac825d31da1005d634f9130fd7512a2f4ab2d13b63eee0ed12dc6a16e727d"

S = "${WORKDIR}"

INSANE_SKIP:${PN} += "already-stripped"


do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/ngrok ${D}${bindir}/ngrok
}

FILES:${PN} += "${bindir}/ngrok"
