import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PINNED_ACTION = re.compile(r"(?m)^\s*uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)")


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
        assert "FROM python:3.15-slim@sha256:" in dockerfile
        assert "pip install --upgrade pip" not in dockerfile

    assert "USER 10001:10001" in app_dockerfile
    assert "pip install --no-cache-dir -r /tmp/chargepilot-build-requirements.txt" in app_dockerfile
    assert "pip install --no-cache-dir --no-deps --no-build-isolation ." in app_dockerfile
    assert "pip install --no-cache-dir -e ." not in app_dockerfile
    assert "COPY connector ./connector" not in app_dockerfile
    assert "COPY agent/windows/install.ps1 ./agent/windows/install.ps1" in app_dockerfile


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
    expected_actions = {
        "actions/checkout",
        "docker/setup-qemu-action",
        "docker/setup-buildx-action",
        "docker/login-action",
        "docker/metadata-action",
        "docker/build-push-action",
        "aquasecurity/trivy-action",
    }
    found_actions = set()

    for workflow_path, tag_format in workflow_paths:
        workflow = workflow_path.read_text()
        actions = PINNED_ACTION.findall(workflow)
        assert actions
        for action, ref in actions:
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                f"{action} in {workflow_path.name} must use a full commit SHA"
            )
            found_actions.add(action)

        assert tag_format in workflow
        assert "provenance: mode=max" in workflow
        assert "sbom: true" in workflow
        assert "outputs.digest" in workflow
        assert "type=raw,value=latest" not in workflow
        assert "DDMMYYYY" not in workflow
        assert (
            "endusercompute/chargepilot" in workflow
            or "endusercompute/chargepilot-connector" in workflow
        )

    assert expected_actions <= found_actions


def test_container_workflows_scan_built_images_and_scope_publishing():
    ci_workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    publish_workflow = (ROOT / ".github" / "workflows" / "publish-deploy.yml").read_text()
    connector_workflow = (ROOT / ".github" / "workflows" / "connector-multiarch.yml").read_text()
    workflows = (ci_workflow, publish_workflow, connector_workflow)

    for workflow in workflows:
        assert "scanners: vuln,secret" in workflow
        assert "severity: CRITICAL,HIGH" in workflow
        assert 'exit-code: "1"' in workflow
        for action, ref in PINNED_ACTION.findall(workflow):
            assert re.fullmatch(r"[0-9a-f]{40}", ref), action

    assert "needs.changes.outputs.api == 'true'" in ci_workflow
    assert "needs.changes.outputs.frontend == 'true'" in ci_workflow
    assert "needs.changes.outputs.connector == 'true'" in ci_workflow
    assert "agent/windows/install\\.ps1" in ci_workflow
    assert "connector/Dockerfile" in connector_workflow
    assert "connector/requirements.txt" in connector_workflow
    assert "connector/*.py" in connector_workflow
    assert ".github/workflows/connector-multiarch.yml" not in connector_workflow
    assert '"git", "diff", "--name-only"' in publish_workflow
    assert "Compare components with their deployed source revisions" in publish_workflow
    assert "API_CHANGED" in publish_workflow
    assert "FRONTEND_CHANGED" in publish_workflow
    assert "Build, scan, and publish ${{ matrix.component }}" in publish_workflow
    assert "dockerfile: ./docker/Dockerfile" in publish_workflow
    assert "dockerfile: ./frontend/Dockerfile" in publish_workflow
    assert "agent/windows/install\\.ps1" in publish_workflow
    assert "Build and push multi-arch image" in publish_workflow
    assert "Scan published AMD64 image for vulnerabilities and secrets" in publish_workflow
    assert "Update GitOps image tags" in publish_workflow
    assert "needs.publish.result == 'success'" in publish_workflow
    publish_job = publish_workflow.split("  publish:\n", 1)[1].split("\n  promote:\n", 1)[0]
    promote_job = publish_workflow.split("  promote:\n", 1)[1]
    assert "contents: read" in publish_job
    assert "contents: write" in promote_job

    for workflow, build_marker, scan_marker in (
        (
            ci_workflow,
            "Build API container image",
            "Scan API image for vulnerabilities and secrets",
        ),
        (
            ci_workflow,
            "Build frontend container image",
            "Scan frontend image for vulnerabilities and secrets",
        ),
        (
            ci_workflow,
            "Build connector container image",
            "Scan connector image for vulnerabilities and secrets",
        ),
        (
            publish_workflow,
            "Build and push multi-arch image",
            "Scan published AMD64 image for vulnerabilities and secrets",
        ),
        (
            connector_workflow,
            "Build and push AMD64 + ARM64 connector image",
            "Scan published connector AMD64 image",
        ),
    ):
        assert workflow.index(build_marker) < workflow.index(scan_marker)


def test_private_kubernetes_images_reference_namespace_pull_secrets():
    manifests = (
        (ROOT / "deploy" / "k3s" / "workloads.yaml", "chargepilot-dockerhub"),
        (ROOT / "deploy" / "k3s" / "docs.yaml", "chargepilot-docs-dockerhub"),
    )
    for manifest_path, secret_name in manifests:
        deployments = [
            document
            for document in manifest_path.read_text().split("\n---")
            if "kind: Deployment" in document
            and "image: endusercompute/chargepilot-" in document
        ]
        assert deployments, f"No private image deployments in {manifest_path}"
        for deployment in deployments:
            assert (
                "      imagePullSecrets:\n"
                f"        - name: {secret_name}\n"
            ) in deployment, (
                f"{manifest_path.name} deployment is missing its private registry "
                f"pull secret {secret_name}"
            )
