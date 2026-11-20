"""Hardware-aware performance profile for the Windows Library Manager.

The default profile is tuned for the user's i3-5005U / 4-logical-processor /
8-GB-RAM computer and a single 7200-rpm library HDD. It deliberately caps
file-level concurrency at two: more concurrent readers can make a single
mechanical disk slower through random seeks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

CPU_LIMIT_PERCENT = 70
PROCESS_MEMORY_LIMIT_GB = 5
MAX_CONCURRENT_FILES = 2
AUDIO_ANALYSIS_SAMPLE_LIMIT = 90_000
HASH_READ_BLOCK_BYTES = 4 * 1024 * 1024
_CACHE_FOLDER_NAME = "POP PUNK GUITAR Library Manager"


def recommended_scan_workers(requested: int | None = None,
                             logical_processors: int | None = None) -> int:
    """Return a safe high-throughput worker count, hard-capped at two files."""
    logical = max(1, int(logical_processors or os.cpu_count() or 1))
    automatic = min(MAX_CONCURRENT_FILES, max(1, logical // 2))
    if requested is None:
        return automatic
    return max(1, min(MAX_CONCURRENT_FILES, logical, int(requested)))


def resolve_fast_cache_dir(fallback: Path) -> Path:
    """Place small, frequently updated scan caches on Windows' local SSD profile.

    Reports and user data retain their existing locations. On non-Windows
    systems, or when LOCALAPPDATA is unavailable, the existing report folder
    remains the safe fallback.
    """
    local_app_data = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    root = (Path(local_app_data) / _CACHE_FOLDER_NAME / "Cache"
            if local_app_data else Path(fallback))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


_RESOURCE_JOB_HANDLE = None


def apply_windows_resource_limits(cpu_percent: int = CPU_LIMIT_PERCENT,
                                  memory_gb: int = PROCESS_MEMORY_LIMIT_GB) -> dict[str, Any]:
    """Apply hard per-process CPU and RAM ceilings using a Windows Job Object.

    The Manager is left untouched on non-Windows platforms. If Windows or an
    enclosing host job refuses assignment, the caller receives a clear status
    and the scan still runs with the bounded two-worker policy.
    """
    global _RESOURCE_JOB_HANDLE
    if os.name != "nt":
        return {
            "applied": False,
            "platform": os.name,
            "reason": "Windows Job Objects are available only on Windows.",
        }
    if not 1 <= int(cpu_percent) <= 100 or int(memory_gb) < 1:
        raise ValueError("Invalid CPU or memory resource limit.")

    import ctypes
    from ctypes import wintypes

    class CpuRateControl(ctypes.Structure):
        _fields_ = [("ControlFlags", wintypes.DWORD),
                    ("CpuRate", wintypes.DWORD)]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return {"applied": False, "reason": f"CreateJobObjectW failed: {ctypes.get_last_error()}"}

    # JobObjectCpuRateControlInformation = 15.
    cpu = CpuRateControl(0x1 | 0x4, int(cpu_percent) * 100)  # ENABLE | HARD_CAP
    if not kernel32.SetInformationJobObject(
        job, 15, ctypes.byref(cpu), ctypes.sizeof(cpu)
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return {"applied": False, "reason": f"CPU limit rejected: Windows error {error}"}

    # JobObjectExtendedLimitInformation = 9; PROCESS_MEMORY_LIMIT = 0x100.
    extended = ExtendedLimitInformation()
    extended.BasicLimitInformation.LimitFlags = 0x100
    extended.ProcessMemoryLimit = int(memory_gb) * 1024 * 1024 * 1024
    if not kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(extended), ctypes.sizeof(extended)
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return {"applied": False, "reason": f"RAM limit rejected: Windows error {error}"}

    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return {
            "applied": False,
            "reason": (
                "Windows refused to assign the Manager to its resource Job Object "
                f"(error {error}); a parent application/job may already control it."
            ),
        }

    # Keep the handle alive for the process lifetime; closing it releases the job.
    _RESOURCE_JOB_HANDLE = job
    return {
        "applied": True,
        "cpu_limit_percent": int(cpu_percent),
        "process_memory_limit_gb": int(memory_gb),
        "worker_limit": MAX_CONCURRENT_FILES,
    }


def performance_profile_text(logical_processors: int | None = None) -> str:
    logical = max(1, int(logical_processors or os.cpu_count() or 1))
    workers = recommended_scan_workers(logical_processors=logical)
    return (
        f"CPU LIMIT {CPU_LIMIT_PERCENT}%  |  RAM LIMIT {PROCESS_MEMORY_LIMIT_GB} GB  |  "
        f"WORKERS {workers}/{MAX_CONCURRENT_FILES}  |  "
        f"LOGICAL CPU {logical}  |  HASH BLOCK {HASH_READ_BLOCK_BYTES // (1024 * 1024)} MB"
    )
