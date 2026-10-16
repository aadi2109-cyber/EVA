"""Single-command install of every Python dependency used by EVA.

    pip install -e .            # runtime deps for contracts, guard and agent backend
    pip install -e ".[dev]"     # + test tooling (pytest, hypothesis)
    pip install -e ".[ml]"      # + Tier-2 detector deps (onnxruntime, numpy, scikit-learn)
    pip install -e ".[all]"     # everything

Requires Python >= 3.11. The per-component pyproject.toml files remain the
source of truth for their own packages; this file unions their dependencies.
"""
from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).parent

# (import root on disk, packages it provides)
_SOURCES = {
    "contracts": "contracts",          # `import contracts`, `contracts.eva_contracts`
    "agent/backend": "app",            # `import app`
    "guard": None,                     # eva_guard, service, admin_api, eval
}

package_dir = {}
packages = []
for root, only in _SOURCES.items():
    found = find_packages(where=root, exclude=["tests", "tests.*"])
    for pkg in found:
        top = pkg.split(".")[0]
        if only is None or top == only or (root == "contracts" and top == "eva_contracts"):
            packages.append(pkg)
            package_dir.setdefault(pkg, f"{root}/{pkg.replace('.', '/')}")

# contracts/ is itself a package (contracts/__init__.py, contracts/models.py)
packages.append("contracts")
package_dir["contracts"] = "contracts"

INSTALL_REQUIRES = [
    # web / API
    "fastapi>=0.110.0",
    "uvicorn>=0.28.0",
    "python-multipart>=0.0.9",
    "httpx>=0.27.0",
    # models / config
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    "pyyaml>=6.0.1",
    # database
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.20.0",
    "alembic>=1.13.0",
    "greenlet>=3.0.0",  # required by SQLAlchemy asyncio
    # security / auth
    "argon2-cffi>=23.1.0",
    "pyjwt>=2.8.0",
    "cryptography>=42.0.0",
    # observability
    "structlog>=24.1.0",
    "prometheus-client>=0.20.0",
]

EXTRAS = {
    "dev": [
        "pytest>=8.0.0",
        "pytest-asyncio>=0.23.0",
        "hypothesis>=6.98.0",
    ],
    # Tier-2 detector (guard/eva_guard/det/t2.py, training scripts) — present on role/sec1
    "ml": [
        "numpy>=1.26.0",
        "onnxruntime>=1.17.0",
        "scikit-learn>=1.4.0",
    ],
}
EXTRAS["all"] = sorted({dep for deps in EXTRAS.values() for dep in deps})

setup(
    name="eva",
    version="0.1.0",
    description="EVA — agent backend, guard and shared contracts",
    long_description=(ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else "",
    python_requires=">=3.11",
    packages=packages,
    package_dir=package_dir,
    include_package_data=True,
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS,
)
