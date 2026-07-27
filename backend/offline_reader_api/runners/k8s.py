"""K8sJobRunner — one ``single-file-cli`` Kubernetes Job per Capture (ADR-0002).

Each Job mounts the shared RWX PVC at ``/data`` (so its Pages land in the same
layout the app serves from) plus a ``/dev/shm`` in-memory ``emptyDir`` for
Chrome. The Job is bounded by ``activeDeadlineSeconds`` (the crawl time cap) and
auto-reaped by ``ttlSecondsAfterFinished``. The app holds namespaced Job RBAC.

``build_job`` is a pure function (no cluster contact) so the Job spec is
unit-testable; the API client is loaded lazily on first use via
``config.load_incluster_config()``.
"""

import secrets

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from offline_reader_api import storage
from offline_reader_api.config import Settings
from offline_reader_api.models import Capture
from offline_reader_api.runner import CaptureProgress

# Fixed Job bounds (ADR-0002). The deadline is the ~45 min crawl time cap.
_ACTIVE_DEADLINE_SECONDS = 2700
_TTL_SECONDS_AFTER_FINISHED = 1800
_BACKOFF_LIMIT = 1
_SHM_SIZE = "512Mi"
_DATA_MOUNT = "/data"


def _max_depth_for(scope_type: str, default_depth: int) -> int:
    """``page`` captures the single root only (depth 0); everything else crawls
    to the configured default depth, with the Scope enforced by the crawler."""
    return 0 if scope_type == "page" else default_depth


def build_job(settings: Settings, capture: Capture, job_name: str) -> "client.V1Job":
    """The V1Job for *capture* — pure (safe to build and assert on off-cluster)."""
    output_dir = f"{_DATA_MOUNT}/captures/{capture.id}/pages"
    env = [
        client.V1EnvVar(name="SEED_URL", value=capture.root_url),
        client.V1EnvVar(
            name="MAX_DEPTH", value=str(_max_depth_for(capture.scope_type, settings.max_depth))
        ),
        client.V1EnvVar(name="OUTPUT_DIR", value=output_dir),
        client.V1EnvVar(name="WORKERS", value=str(settings.workers)),
        client.V1EnvVar(name="WAIT_MS", value=str(settings.wait_ms)),
        client.V1EnvVar(name="MAX_PAGES", value=str(capture.max_pages)),
        client.V1EnvVar(name="SCOPE_TYPE", value=capture.scope_type),
    ]
    container = client.V1Container(
        name="capture",
        image=settings.singlefile_image,
        env=env,
        resources=client.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "1Gi"},
            limits={"memory": "2Gi"},
        ),
        volume_mounts=[
            client.V1VolumeMount(name="data", mount_path=_DATA_MOUNT),
            client.V1VolumeMount(name="dshm", mount_path="/dev/shm"),
        ],
    )
    pod_spec = client.V1PodSpec(
        restart_policy="Never",
        containers=[container],
        volumes=[
            client.V1Volume(
                name="data",
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=settings.nfs_pvc_claim
                ),
            ),
            client.V1Volume(
                name="dshm",
                empty_dir=client.V1EmptyDirVolumeSource(medium="Memory", size_limit=_SHM_SIZE),
            ),
        ],
    )
    return client.V1Job(
        metadata=client.V1ObjectMeta(
            name=job_name,
            labels={"app": "offline-reader", "offline-reader/capture": capture.id},
        ),
        spec=client.V1JobSpec(
            active_deadline_seconds=_ACTIVE_DEADLINE_SECONDS,
            ttl_seconds_after_finished=_TTL_SECONDS_AFTER_FINISHED,
            backoff_limit=_BACKOFF_LIMIT,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"app": "offline-reader", "offline-reader/capture": capture.id}
                ),
                spec=pod_spec,
            ),
        ),
    )


class K8sJobRunner:
    """Runs each Capture as its own namespaced Kubernetes Job."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._batch: client.BatchV1Api | None = None

    def _api(self) -> "client.BatchV1Api":
        """Lazily load in-cluster config and cache the Batch API client."""
        if self._batch is None:
            config.load_incluster_config()
            self._batch = client.BatchV1Api()
        return self._batch

    def start(self, capture: Capture) -> str:
        # A fresh suffix each start so a Refresh never collides with a not-yet-
        # reaped previous Job of the same Capture.
        job_name = f"offline-capture-{capture.id[:12]}-{secrets.token_hex(3)}"
        self._api().create_namespaced_job(
            namespace=self.settings.pod_namespace,
            body=build_job(self.settings, capture, job_name),
        )
        return job_name

    def poll(self, capture: Capture) -> CaptureProgress:
        count, size = storage.count_pages(
            storage.pages_dir(self.settings.data_dir, capture.id)
        )
        if not capture.job_name:
            return CaptureProgress(status="queued", page_count=count, size_bytes=size)
        try:
            job = self._api().read_namespaced_job_status(
                name=capture.job_name, namespace=self.settings.pod_namespace
            )
        except ApiException as exc:
            if exc.status == 404:
                # TTL-reaped: infer terminal state from what landed on disk.
                if count > 0:
                    return CaptureProgress(status="done", page_count=count, size_bytes=size)
                return CaptureProgress(
                    status="failed", page_count=count, size_bytes=size, error="job not found"
                )
            raise
        job_status = job.status
        if job_status is not None and job_status.succeeded:
            return CaptureProgress(status="done", page_count=count, size_bytes=size)
        if job_status is not None and job_status.failed:
            return CaptureProgress(
                status="failed", page_count=count, size_bytes=size, error="job failed"
            )
        return CaptureProgress(status="crawling", page_count=count, size_bytes=size)

    def cancel(self, capture: Capture) -> None:
        if not capture.job_name:
            return
        try:
            self._api().delete_namespaced_job(
                name=capture.job_name,
                namespace=self.settings.pod_namespace,
                propagation_policy="Background",
            )
        except ApiException as exc:
            if exc.status != 404:
                raise
