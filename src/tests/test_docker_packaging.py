"""Ensure Docker image includes everything needed for production."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def test_dockerfile_copies_locales():
    dockerfile = (SRC / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY src/locales" in dockerfile, "Dockerfile must COPY src/locales/ for i18n in containers"


def test_docker_compose_has_panel_and_bridge():
    compose = (SRC / "docker" / "compose.yml").read_text(encoding="utf-8")
    assert "panel:" in compose
    assert "whatsapp-bridge:" in compose


def test_governance_files_exist():
    required = [
        "src/LICENSE",
        "README.md",
        "src/docs/CONTRIBUTING.md",
        "src/docs/SECURITY.md",
        ".github/CODE_OF_CONDUCT.md",
        "src/docs/CHANGELOG.md",
        "src/docs/SUPPORT.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/workflows/ci.yml",
    ]
    for name in required:
        assert (ROOT / name).is_file(), f"Missing governance file: {name}"
    for name in ("src/scripts/install.sh", "src/scripts/start.sh", "src/scripts/stop.sh", "src/scripts/smoke_local.sh"):
        path = ROOT / name
        assert path.is_file(), f"Missing {name}"
        assert path.stat().st_mode & 0o111, f"{name} should be executable"
