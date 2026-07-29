SUMMARY = "FastAPI framework"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "https://files.pythonhosted.org/packages/py3/f/fastapi/fastapi-0.110.0-py3-none-any.whl;downloadfilename=fastapi-0.110.0-py3-none-any.zip;subdir=fastapi-0.110.0"
SRC_URI[sha256sum] = "87a1f6fb632a218222c5984be540055346a8f5d8a68e8f6fb647b1dc9934de4b"

inherit python3native

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    cp -r ${WORKDIR}/fastapi-0.110.0/* ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}"

RDEPENDS:${PN} += " \
    python3-starlette \
    python3-pydantic \
    python3-typing-extensions \
"
