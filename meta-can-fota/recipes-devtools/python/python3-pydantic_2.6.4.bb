SUMMARY = "Data validation and settings management using python type hints"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "https://files.pythonhosted.org/packages/py3/p/pydantic/pydantic-2.6.4-py3-none-any.whl;downloadfilename=pydantic-2.6.4-py3-none-any.zip;subdir=pydantic-2.6.4"
SRC_URI[sha256sum] = "cc46fce86607580867bdc3361ad462bab9c222ef042d3da86f2fb333e1d916c5"

inherit python3native

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    cp -r ${WORKDIR}/pydantic-2.6.4/* ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}"

RDEPENDS:${PN} += " \
    python3-core \
    python3-typing-extensions \
    python3-pydantic-core \
"
