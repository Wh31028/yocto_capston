SUMMARY = "ngrok - reverse proxy for secure tunnels"
HOMEPAGE = "https://ngrok.com"
LICENSE = "CLOSED"

SRC_URI = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz;downloadfilename=ngrok-v3-stable-linux-arm.tgz"
SRC_URI[sha256sum] = "a23e84d4706587740a5d590fa57fc42e289f2fd23c8694e9265a398890efb753"

S = "${WORKDIR}"

INSANE_SKIP:${PN} += "already-stripped"


do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/ngrok ${D}${bindir}/ngrok
}

FILES:${PN} += "${bindir}/ngrok"
