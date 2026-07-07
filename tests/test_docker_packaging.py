"""Ensure Docker image includes everything needed for production."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_copies_locales():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY locales" in dockerfile, "Dockerfile must COPY locales/ for i18n in containers"


def test_docker_compose_has_panel_and_bridge():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "panel:" in compose
    assert "whatsapp-bridge:" in compose


def test_governance_files_exist():
    required = [
        "LICENSE",
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "SUPPORT.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/workflows/ci.yml",
    ]
    for name in required:
        assert (ROOT / name).is_file(), f"Missing governance file: {name}"
    for name in ("install.sh", "start.sh", "stop.sh", "scripts/smoke_local.sh"):
        path = ROOT / name
        assert path.is_file(), f"Missing {name}"
        assert path.stat().st_mode & 0o111, f"{name} should be executable"
