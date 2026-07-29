SUMMARY = "A pure-Python, bring-your-own-I/O implementation of HTTP/1.1"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "https://files.pythonhosted.org/packages/py3/h/h11/h11-0.14.0-py3-none-any.whl;downloadfilename=h11-0.14.0-py3-none-any.zip;subdir=h11-0.14.0"
SRC_URI[sha256sum] = "e3fe4ac4b851c468cc8363d500db52c2ead036020723024a109d37346efaa761"

inherit python3native

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    cp -r ${WORKDIR}/h11-0.14.0/* ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}"
