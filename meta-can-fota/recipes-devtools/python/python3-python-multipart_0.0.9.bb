SUMMARY = "streaming multipart parser for Python"
HOMEPAGE = "https://github.com/Kludex/python-multipart"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

SRC_URI = "https://files.pythonhosted.org/packages/py3/p/python_multipart/python_multipart-0.0.9-py3-none-any.whl;downloadfilename=python_multipart-0.0.9-py3-none-any.whl;unpack=0"
SRC_URI[sha256sum] = "97ca7b8ea7b05f977dc3849c3ba99d51689822fab725c3703af7c866a0c2b215"

S = "${WORKDIR}"

inherit allarch

DEPENDS += "unzip-native"


do_install() {
    install -d ${D}${libdir}/python3.12/site-packages
    unzip -q -o ${WORKDIR}/python_multipart-0.0.9-py3-none-any.whl -d ${D}${libdir}/python3.12/site-packages
    rm -rf ${D}${libdir}/python3.12/site-packages/*.dist-info/RECORD
}

FILES:${PN} += "${libdir}/python3.12/site-packages/*"

RDEPENDS:${PN} += "python3-core"
