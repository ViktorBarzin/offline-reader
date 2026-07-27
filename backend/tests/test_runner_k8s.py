"""K8sJobRunner.build_job is pure (no cluster contact) — assert the Job spec
carries the right env, mounts, bounds and resources (ADR-0002)."""

from offline_reader_api.config import Settings
from offline_reader_api.models import Capture
from offline_reader_api.runners.k8s import build_job


def _capture(scope_type: str = "prefix") -> Capture:
    return Capture(
        id="abc123def456",
        root_url="https://docs.example.com/",
        title="https://docs.example.com/",
        scope_type=scope_type,
        max_pages=250,
        status="queued",
        page_count=0,
        size_bytes=0,
    )


def _settings() -> Settings:
    return Settings(
        data_dir="/data",
        capture_mode="k8s",
        pod_namespace="offline-reader",
        singlefile_image="ghcr.io/viktorbarzin/offline-reader-capture:v1",
        nfs_pvc_claim="offline-reader",
        max_depth=3,
        workers=2,
        wait_ms=500,
    )


def test_job_env_and_output_dir() -> None:
    job = build_job(_settings(), _capture(), "offline-capture-abc-xyz")
    container = job.spec.template.spec.containers[0]
    env = {e.name: e.value for e in container.env}
    assert env["SEED_URL"] == "https://docs.example.com/"
    assert env["OUTPUT_DIR"] == "/data/captures/abc123def456/pages"
    assert env["MAX_PAGES"] == "250"
    assert env["SCOPE_TYPE"] == "prefix"
    assert env["MAX_DEPTH"] == "3"
    assert env["WORKERS"] == "2"
    assert env["WAIT_MS"] == "500"
    assert container.image == "ghcr.io/viktorbarzin/offline-reader-capture:v1"


def test_page_scope_crawls_depth_zero() -> None:
    job = build_job(_settings(), _capture(scope_type="page"), "j")
    env = {e.name: e.value for e in job.spec.template.spec.containers[0].env}
    assert env["MAX_DEPTH"] == "0"


def test_job_bounds_and_restart_policy() -> None:
    job = build_job(_settings(), _capture(), "j")
    assert job.spec.active_deadline_seconds == 2700
    assert job.spec.ttl_seconds_after_finished == 1800
    assert job.spec.backoff_limit == 1
    assert job.spec.template.spec.restart_policy == "Never"
    assert job.metadata.name == "j"


def test_job_mounts_pvc_and_shm() -> None:
    pod = build_job(_settings(), _capture(), "j").spec.template.spec
    mounts = {m.name: m.mount_path for m in pod.containers[0].volume_mounts}
    assert mounts == {"data": "/data", "dshm": "/dev/shm"}
    volumes = {v.name: v for v in pod.volumes}
    assert volumes["data"].persistent_volume_claim.claim_name == "offline-reader"
    assert volumes["dshm"].empty_dir.medium == "Memory"
    assert volumes["dshm"].empty_dir.size_limit == "512Mi"


def test_job_resources() -> None:
    resources = build_job(_settings(), _capture(), "j").spec.template.spec.containers[0].resources
    assert resources.requests == {"cpu": "500m", "memory": "1Gi"}
    assert resources.limits == {"memory": "2Gi"}
