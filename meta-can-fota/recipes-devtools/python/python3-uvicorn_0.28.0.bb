SUMMARY = "The lightning-fast ASGI server."
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/BSD-3-Clause;md5=550794465ba0ec5312d6919e203a55f9"

SRC_URI = "https://files.pythonhosted.org/packages/py3/u/uvicorn/uvicorn-0.28.0-py3-none-any.whl;downloadfilename=uvicorn-0.28.0-py3-none-any.zip;subdir=uvicorn-0.28.0"
SRC_URI[sha256sum] = "6623abbbe6176204a4226e67607b4d52cc60ff62cda0ff177613645cefa2ece1"

inherit python3native

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    cp -r ${WORKDIR}/uvicorn-0.28.0/* ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}"

RDEPENDS:${PN} += " \
    python3-click \
    python3-h11 \
    python3-asyncio \
"
