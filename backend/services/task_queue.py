import os
import queue
import subprocess
import threading
import time
import traceback
import uuid

from backend import runtime
from backend.services import model_gallery, video_reconstruction
from backend.services.model_convert import ply_to_spz
from backend.services.model_orientation import VIEWER_ORIENTATION_DEFAULT
from backend.services.workspace_lock import WorkspaceInstanceLock

TASK_RETENTION_SECONDS = 3600
CLEANUP_INTERVAL = 300
TASK_KIND_IMAGE_SHARP = "image_sharp"


class TaskManager:
    def __init__(
        self,
        *,
        paths,
        thumbnail_generator=None,
        sharp_device_selector=None,
        sharp_command_resolver=None,
        spz_converter=None,
        verbose_log=None,
        cleanup_interval=CLEANUP_INTERVAL,
        retention_seconds=TASK_RETENTION_SECONDS,
    ):
        self.paths = paths
        self.thumbnail_generator = thumbnail_generator
        self.sharp_device_selector = sharp_device_selector or runtime.select_sharp_device
        self.sharp_command_resolver = sharp_command_resolver or runtime.resolve_sharp_command
        self.spz_converter = spz_converter or ply_to_spz
        self.verbose_log = verbose_log or runtime.verbose_log
        self.cleanup_interval = cleanup_interval
        self.retention_seconds = retention_seconds

        self.task_queue = queue.Queue()
        self.task_status = {}
        self.task_lock = threading.Lock()
        self.running_processes = {}
        self._workers_started = False
        self._cleanup_started = False
        self._start_lock = threading.Lock()
        self._workspace_lock = WorkspaceInstanceLock(paths.workspace_folder)

    def set_thumbnail_generator(self, thumbnail_generator):
        self.thumbnail_generator = thumbnail_generator

    def _write_image_metadata(self, model_id, display_filename, generation_status):
        source_name = str(display_filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        display_name = os.path.splitext(source_name)[0] or model_id
        existing_metadata = model_gallery.read_model_metadata(self.paths, model_id)
        return model_gallery.write_model_metadata(
            self.paths,
            model_id,
            {
                **existing_metadata,
                "display_name": display_name,
                "source_media_type": "image",
                "viewer_orientation": VIEWER_ORIENTATION_DEFAULT,
                "source_name": source_name,
                "generation_status": generation_status,
            },
        )

    def _update_image_metadata_status(self, task_id, generation_status):
        with self.task_lock:
            task = dict(self.task_status.get(task_id) or {})
        if (task.get("kind") or TASK_KIND_IMAGE_SHARP) != TASK_KIND_IMAGE_SHARP:
            return

        input_filename = task.get("input_filename") or os.path.basename(task.get("input_path", ""))
        model_id = task.get("model_id") or os.path.splitext(input_filename)[0]
        display_filename = task.get("filename") or input_filename
        if not model_id:
            return

        try:
            self._write_image_metadata(model_id, display_filename, generation_status)
        except Exception as exc:
            runtime.log(
                "WARN",
                f"Task {task_id} failed to save image metadata status {generation_status}: {exc}",
            )

    def enqueue_file(self, input_path, filename, display_filename=None):
        if self.thumbnail_generator:
            self.thumbnail_generator(input_path, filename)

        task_id = str(uuid.uuid4())
        resolved_display_filename = display_filename or filename
        model_id = os.path.splitext(filename)[0]
        self._write_image_metadata(model_id, resolved_display_filename, "pending")
        task_info = {
            "id": task_id,
            "kind": TASK_KIND_IMAGE_SHARP,
            "status": "pending",
            "filename": resolved_display_filename,
            "input_filename": filename,
            "model_id": model_id,
            "input_path": input_path,
            "output_folder": self.paths.output_folder,
            "created_at": time.time(),
            "error": None,
        }

        with self.task_lock:
            self.task_status[task_id] = task_info
        self.task_queue.put(task_id)
        runtime.log(
            "INFO",
            f"Queued image task {task_id}: filename={resolved_display_filename} input={input_path}",
        )
        return self._public_task(task_info)

    def enqueue_video_reconstruction(self, task_payload):
        task_id = str(uuid.uuid4())
        task_info = {
            "id": task_id,
            "kind": video_reconstruction.TASK_KIND_VIDEO_3DGS,
            "status": "pending",
            "created_at": time.time(),
            "error": None,
            **task_payload,
        }

        with self.task_lock:
            self.task_status[task_id] = task_info
        self.task_queue.put(task_id)
        runtime.log(
            "INFO",
            "Queued video reconstruction task "
            f"{task_id}: filename={task_info.get('filename')} source={task_info.get('source_video_path')}",
        )
        return self._public_task(task_info)

    def list_tasks(self):
        with self.task_lock:
            tasks = [self._public_task(task) for task in self.task_status.values()]
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        has_active = any(t["status"] in ("pending", "running", "processing") for t in tasks)
        return tasks, has_active

    def cancel_task(self, task_id):
        process_to_kill = None
        kill_process_tree = False
        cancelled_immediately = False
        with self.task_lock:
            task = self.task_status.get(task_id)
            if not task:
                return {"success": False, "error": "Task not found"}, 404

            if task["status"] == "pending":
                task["status"] = "cancelled"
                cancelled_immediately = True

            elif task["status"] in ("running", "processing"):
                task["status"] = "cancelled"
                process_to_kill = self.running_processes.get(task_id)
                kill_process_tree = (
                    task.get("kind") == video_reconstruction.TASK_KIND_VIDEO_3DGS
                )
            else:
                return {"success": False, "error": f"Task already {task['status']}"}, 400

        self._update_image_metadata_status(task_id, "cancelled")
        if cancelled_immediately:
            return {"success": True, "message": "Task cancelled"}, 200

        # Terminate outside the lock so a slow kill never blocks status reads.
        if process_to_kill is not None:
            if kill_process_tree:
                # Video tasks spawn their own process group/session, so killing
                # the whole tree is safe and prevents orphaned GPU workers.
                video_reconstruction.terminate_process_tree(process_to_kill)
            else:
                try:
                    process_to_kill.terminate()
                except Exception:
                    pass
        return {"success": True, "message": "Task cancellation requested"}, 200

    def cleanup_old_tasks(self):
        """定期清理已完成的旧任务，防止内存泄漏。"""
        while True:
            time.sleep(self.cleanup_interval)
            cutoff = time.time() - self.retention_seconds
            with self.task_lock:
                old_ids = [
                    task_id for task_id, task in self.task_status.items()
                    if task["created_at"] < cutoff and task["status"] in ("completed", "failed", "cancelled")
                ]
                for task_id in old_ids:
                    del self.task_status[task_id]
                if old_ids:
                    print(f"🧹 Cleaned up {len(old_ids)} old tasks")

    def worker(self):
        """后台工作线程，持续处理队列中的任务。"""
        print("👷 Worker thread started...")
        while True:
            task_id = self.task_queue.get()
            if task_id is None:
                break

            with self.task_lock:
                task = self.task_status.get(task_id)
                if not task or task["status"] == "cancelled":
                    self.task_queue.task_done()
                    continue
                filename = task["filename"]
                input_filename = task.get("input_filename") or os.path.basename(task.get("input_path", ""))
                kind = task.get("kind") or TASK_KIND_IMAGE_SHARP

            print(f"🔄 Processing task {task_id}: {filename}")
            with self.task_lock:
                now = time.time()
                self.task_status[task_id]["status"] = "processing"
                self.task_status[task_id]["progress"] = None
                self.task_status[task_id]["stage"] = "starting"
                self.task_status[task_id]["started_at"] = now
                self.task_status[task_id]["stage_started_at"] = now

            if kind == video_reconstruction.TASK_KIND_VIDEO_3DGS:
                video_reconstruction.run_video_reconstruction_task(self, task_id, task)
                self.task_queue.task_done()
                continue

            if kind != TASK_KIND_IMAGE_SHARP:
                runtime.log("ERROR", f"Task {task_id} failed: unsupported task kind {kind}")
                with self.task_lock:
                    self.task_status[task_id]["status"] = "failed"
                    self.task_status[task_id]["error"] = f"Unsupported task kind: {kind}"
                self.task_queue.task_done()
                continue

            self._update_image_metadata_status(task_id, "processing")
            input_path = task["input_path"]
            output_folder = task["output_folder"]

            device = self.sharp_device_selector()
            print(f"Using Sharp device: {device}")
            sharp_command = self.sharp_command_resolver()
            print(f"Using Sharp command: {sharp_command}")

            cmd = [
                sharp_command,
                "predict",
                "-i",
                input_path,
                "-o",
                output_folder,
                "--device",
                device,
            ]

            process = None
            try:
                process_env = os.environ.copy()
                process_env.setdefault("PYTHONUTF8", "1")
                process_env.setdefault("PYTHONIOENCODING", "utf-8")
                self.verbose_log(f"Task {task_id} input_path={input_path} exists={os.path.exists(input_path)}")
                self.verbose_log(f"Task {task_id} output_folder={output_folder} exists={os.path.exists(output_folder)}")
                self.verbose_log(f"Task {task_id} command={runtime.format_command_for_log(cmd)}")
                self.verbose_log(f"Task {task_id} subprocess_cwd={os.getcwd()}")
                self.verbose_log(f"Task {task_id} subprocess_path={process_env.get('PATH', '')}")
                runtime.log("INFO", f"Task {task_id} launching Sharp: {runtime.format_command_for_log(cmd)}")

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=process_env,
                )

                with self.task_lock:
                    self.running_processes[task_id] = process

                output_lines = []
                cancelled = False
                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break

                    with self.task_lock:
                        if self.task_status.get(task_id, {}).get("status") == "cancelled":
                            cancelled = True
                            break

                    output_lines.append(line)
                    runtime.log("DEBUG", f"Task {task_id} | {line.rstrip()}")
                    self._update_progress_from_line(task_id, input_filename, line)

                if cancelled:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()
                    print(f"🛑 Task {task_id} cancelled by user.")
                    self.task_queue.task_done()
                    continue

                process.stdout.close()
                return_code = process.wait()
                self._finish_process(task_id, input_filename, output_folder, return_code, output_lines)

            except Exception as exc:
                error_text = traceback.format_exc()
                task_failed = False
                with self.task_lock:
                    if self.task_status.get(task_id, {}).get("status") != "cancelled":
                        self.task_status[task_id]["status"] = "failed"
                        self.task_status[task_id]["error"] = error_text
                        task_failed = True
                if task_failed:
                    self._update_image_metadata_status(task_id, "failed")
                print(f"❌ Task {task_id} exception: {exc}")
                runtime.log("ERROR", f"Task {task_id} exception traceback:\n{error_text}")
            finally:
                with self.task_lock:
                    self.running_processes.pop(task_id, None)

            self.task_queue.task_done()

    def _public_task(self, task):
        public = {
            "id": task.get("id"),
            "filename": task.get("filename"),
            "status": task.get("status"),
            "progress": task.get("progress"),
            "stage": task.get("stage"),
            "error": self._sanitize_public_text(task, task.get("error")),
            "created_at": task.get("created_at"),
        }

        optional_keys = (
            "kind",
            "source_media_id",
            "source_name",
            "mode",
            "quality",
            "custom_options",
            "engine",
            "resolved_engine",
            "vram_budget",
            "output_name",
            "error_code",
            "started_at",
            "completed_at",
        )
        for key in optional_keys:
            if task.get(key) is not None:
                public[key] = task.get(key)

        details = task.get("details")
        if isinstance(details, dict):
            safe_details = {}
            if isinstance(details.get("warnings"), list):
                safe_details["warnings"] = details["warnings"]
            if isinstance(details.get("viewer_url"), str):
                safe_details["viewer_url"] = details["viewer_url"]
            if isinstance(details.get("viewer_port"), int):
                safe_details["viewer_port"] = details["viewer_port"]
            public["details"] = safe_details

        return {key: value for key, value in public.items() if value is not None}

    def _sanitize_public_text(self, task, value):
        if not isinstance(value, str):
            return value

        sanitized = value
        sensitive_paths = [
            task.get("input_path"),
            task.get("output_folder"),
            task.get("source_video_path"),
            task.get("output_path"),
            task.get("spz_path"),
            self.paths.workspace_folder,
            self.paths.input_folder,
            self.paths.output_folder,
            self.paths.video_reconstruction_folder,
        ]
        for path in sensitive_paths:
            if isinstance(path, str) and path:
                sanitized = sanitized.replace(path, "[path]")
        return sanitized

    def _update_progress_from_line(self, task_id, filename, line):
        line_lower = line.lower()
        with self.task_lock:
            if "no checkpoint provided. downloading default model" in line_lower:
                # torch.hub prints this before it checks the local cache, even
                # when no network download is needed.
                self.task_status[task_id]["progress"] = None
                self.task_status[task_id]["stage"] = "modelCache"
            elif line_lower.strip().startswith("downloading:"):
                self.task_status[task_id]["progress"] = None
                self.task_status[task_id]["stage"] = "downloading"
            elif "loading checkpoint" in line_lower or "using preset" in line_lower:
                self.task_status[task_id]["progress"] = None
                self.task_status[task_id]["stage"] = "modelLoading"
            elif "processing" in line_lower and filename.split(".")[0].lower() in line_lower:
                self.task_status[task_id]["progress"] = 15
                self.task_status[task_id]["stage"] = "processing"
            elif "preprocessing" in line_lower:
                self.task_status[task_id]["progress"] = 25
                self.task_status[task_id]["stage"] = "preprocessing"
            elif "inference" in line_lower:
                self.task_status[task_id]["progress"] = 50
                self.task_status[task_id]["stage"] = "inference"
            elif "postprocessing" in line_lower:
                self.task_status[task_id]["progress"] = 80
                self.task_status[task_id]["stage"] = "postprocessing"
            elif "saving" in line_lower:
                self.task_status[task_id]["progress"] = 95
                self.task_status[task_id]["stage"] = "saving"

    def _finish_process(self, task_id, filename, output_folder, return_code, output_lines):
        with self.task_lock:
            if self.task_status.get(task_id, {}).get("status") == "cancelled":
                return

        if return_code == 0:
            name_without_ext = os.path.splitext(filename)[0]
            expected_ply = os.path.join(output_folder, name_without_ext + ".ply")

            ply_exists = os.path.exists(expected_ply)
            if not ply_exists:
                with self.task_lock:
                    if self.task_status.get(task_id, {}).get("status") == "cancelled":
                        return
                    self.task_status[task_id]["status"] = "failed"
                    self.task_status[task_id]["error"] = "Output file not found after execution."
                self._update_image_metadata_status(task_id, "failed")
                print(f"❌ Task {task_id} failed: Output missing.")
                runtime.log("ERROR", f"Task {task_id} failed: output file missing at {expected_ply}")
                return

            with self.task_lock:
                if self.task_status.get(task_id, {}).get("status") == "cancelled":
                    return
                self.task_status[task_id]["progress"] = 98
                self.task_status[task_id]["stage"] = "postprocessing"

            try:
                spz_result = self.spz_converter(expected_ply)
                if spz_result:
                    ply_size = os.path.getsize(expected_ply)
                    spz_size = os.path.getsize(spz_result)
                    ratio = 100 - spz_size * 100 // ply_size if ply_size > 0 else 0
                    print(f"📦 SPZ converted: {ply_size/1024:.0f}KB → {spz_size/1024:.0f}KB ({ratio}% smaller)")
            except Exception as exc:
                print(f"⚠️ SPZ auto-convert failed for {name_without_ext}: {exc}")
                runtime.log("WARN", f"Task {task_id} SPZ auto-convert failed for {name_without_ext}: {exc}")

            with self.task_lock:
                if self.task_status.get(task_id, {}).get("status") == "cancelled":
                    return

            self._update_image_metadata_status(task_id, "completed")
            try:
                from backend.services import model_assets

                model_assets.sync_generated_model_asset(self.paths, name_without_ext)
            except Exception as exc:
                runtime.log("WARN", f"Model asset catalog sync failed after task {task_id}: {exc}")
            with self.task_lock:
                if self.task_status.get(task_id, {}).get("status") == "cancelled":
                    return
                self.task_status[task_id]["status"] = "completed"
                self.task_status[task_id]["progress"] = 100
                self.task_status[task_id]["stage"] = "done"
            print(f"✅ Task {task_id} completed successfully.")
            runtime.log("INFO", f"Task {task_id} completed successfully: {expected_ply}")
            return

        stderr_output = "".join(output_lines)
        with self.task_lock:
            task_failed = False
            if self.task_status.get(task_id, {}).get("status") != "cancelled":
                self.task_status[task_id]["status"] = "failed"
                self.task_status[task_id]["error"] = stderr_output if stderr_output else "Unknown error"
                task_failed = True
        if task_failed:
            self._update_image_metadata_status(task_id, "failed")
        print(f"❌ Task {task_id} failed with return code {return_code}")
        runtime.log("ERROR", f"Task {task_id} failed with return code {return_code}")
        if stderr_output:
            print(f"   Error output:\n{stderr_output}")
            runtime.log("ERROR", f"Task {task_id} subprocess output:\n{stderr_output}")

    def start_workers(self):
        """Start worker and cleanup threads once."""
        with self._start_lock:
            if not self._workers_started and not self._cleanup_started:
                self._workspace_lock.acquire()
                try:
                    self._cleanup_interrupted_runtime()
                except Exception:
                    self._workspace_lock.release()
                    raise
            if not self._workers_started:
                threading.Thread(target=self.worker, daemon=True).start()
                self._workers_started = True
            if not self._cleanup_started:
                threading.Thread(target=self.cleanup_old_tasks, daemon=True).start()
                self._cleanup_started = True

    def _cleanup_interrupted_runtime(self):
        image_cleanup = model_gallery.cleanup_interrupted_image_tasks(self.paths)
        if image_cleanup["removed"] or image_cleanup["recovered"]:
            runtime.log(
                "INFO",
                "Reconciled interrupted image tasks at startup: "
                f"removed={image_cleanup['removed']} recovered={image_cleanup['recovered']}",
            )
        if image_cleanup["errors"]:
            runtime.log(
                "WARN",
                f"Failed to reconcile {image_cleanup['errors']} interrupted image task(s)",
            )
        video_reconstruction.cleanup_stale_runtime_artifacts(self.paths)

    def release_workspace_lock(self):
        """Release the workspace lock after the HTTP server stops."""
        self._workspace_lock.release()

    @property
    def workers_started(self):
        return self._workers_started
