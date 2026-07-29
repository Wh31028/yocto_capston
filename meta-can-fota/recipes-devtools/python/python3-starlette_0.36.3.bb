SUMMARY = "The little ASGI framework that shines."
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/BSD-3-Clause;md5=550794465ba0ec5312d6919e203a55f9"

SRC_URI = "https://files.pythonhosted.org/packages/py3/s/starlette/starlette-0.36.3-py3-none-any.whl;downloadfilename=starlette-0.36.3-py3-none-any.zip;subdir=starlette-0.36.3"
SRC_URI[sha256sum] = "13d429aa93a61dc40bf503e8c801db1f1bca3dc706b10ef2434a36123568f044"

inherit python3native

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    cp -r ${WORKDIR}/starlette-0.36.3/* ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}"

RDEPENDS:${PN} += " \
    python3-anyio \
"
