from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_build_context_excludes_secrets_and_runtime_data():
    dockerignore = (ROOT / ".dockerignore").read_text()

    for pattern in (
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "!.env.example",
        "!connector/.env.example",
        "*.pem",
        "*.key",
        "connector-config.json",
        "connector-data",
    ):
        assert pattern in dockerignore


def test_dockerfiles_use_pinned_images_and_unprivileged_runtime():
    app_dockerfile = (ROOT / "docker" / "Dockerfile").read_text()
    connector_dockerfile = (ROOT / "connector" / "Dockerfile").read_text()

    for dockerfile in (app_dockerfile, connector_dockerfile):
        assert "FROM python:3.12-slim@sha256:" in dockerfile
        assert "pip install --upgrade pip" not in dockerfile

    assert "USER 10001:10001" in app_dockerfile
    assert "pip install --no-cache-dir ." in app_dockerfile
    assert "pip install --no-cache-dir -e ." not in app_dockerfile


def test_compose_services_apply_container_hardening():
    app_compose = (ROOT / "docker-compose.yml").read_text()
    connector_compose = (ROOT / "connector" / "docker-compose.yml").read_text()

    assert "postgres:16-alpine@sha256:" in app_compose
    for compose in (app_compose, connector_compose):
        assert "read_only: true" in compose
        assert "cap_drop:\n      - ALL" in compose
        assert "no-new-privileges:true" in compose
        assert "noexec,nosuid" in compose

    assert "network_mode: host" in connector_compose


def test_image_workflows_pin_actions_and_publish_digest_references():
    workflow_paths = (
        (
            ROOT / ".github" / "workflows" / "publish-deploy.yml",
            "type=raw,value=sha-",
        ),
        (
            ROOT / ".github" / "workflows" / "connector-multiarch.yml",
            "type=sha,format=long",
        ),
    )
    expected_actions = (
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
        "docker/setup-qemu-action@49b3bc8e6bdd4a60e6116a5414239cba5943d3cf",
        "docker/setup-buildx-action@e468171a9de216ec08956ac3ada2f0791b6bd435",
        "docker/login-action@74a5d142397b4f367a81961eba4e8cd7edddf772",
        "docker/metadata-action@c1e51972afc2121e065aed6d45c65596fe445f3f",
        "docker/build-push-action@263435318d21b8e681c14492fe198d362a7d2c83",
    )

    for workflow_path, tag_format in workflow_paths:
        workflow = workflow_path.read_text()
        assert tag_format in workflow
        assert "provenance: mode=max" in workflow
        assert "sbom: true" in workflow
        assert "steps.build.outputs.digest" in workflow
        assert "type=raw,value=latest" not in workflow
        assert "DDMMYYYY" not in workflow
        assert (
            "endusercompute/chargepilot" in workflow
            or "endusercompute/chargepilot-connector" in workflow
        )
        for action in expected_actions:
            assert action in workflow
