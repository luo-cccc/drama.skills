#!/usr/bin/env python3
"""Handle-relative Windows filesystem access for the short-drama dashboard."""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import BinaryIO, NamedTuple


if os.name != "nt":
    raise ImportError("windows_secure_fs is only available on Windows")

import msvcrt  # noqa: E402
from ctypes import wintypes  # noqa: E402


FILE_READ_DATA = 0x0001
FILE_LIST_DIRECTORY = 0x0001
FILE_WRITE_DATA = 0x0002
FILE_READ_ATTRIBUTES = 0x0080
DELETE = 0x00010000
SYNCHRONIZE = 0x00100000

FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
FILE_SHARE_ALL = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE

FILE_OPEN = 0x00000001
FILE_CREATE = 0x00000002
FILE_OPEN_IF = 0x00000003
FILE_DIRECTORY_FILE = 0x00000001
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_OPEN_REPARSE_POINT = 0x00200000

FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

OBJ_CASE_INSENSITIVE = 0x00000040
FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
FILE_ID_BOTH_DIRECTORY_INFO_CLASS = 10
FILE_ID_BOTH_DIRECTORY_RESTART_INFO_CLASS = 11
FILE_STANDARD_INFO_CLASS = 1
FILE_RENAME_INFORMATION_EX_CLASS = 65
FILE_DISPOSITION_INFORMATION_CLASS = 13

FILE_RENAME_REPLACE_IF_EXISTS = 0x00000001
FILE_RENAME_POSIX_SEMANTICS = 0x00000002

FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
OPEN_EXISTING = 3
DRIVE_FIXED = 3
ERROR_NO_MORE_FILES = 18
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UnicodeString)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class _IoStatusBlock(ctypes.Structure):
    _fields_ = [
        ("Status", ctypes.c_ssize_t),
        ("Information", ctypes.c_size_t),
    ]


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


class _FileStandardInfo(ctypes.Structure):
    _fields_ = [
        ("AllocationSize", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("NumberOfLinks", wintypes.DWORD),
        ("DeletePending", wintypes.BOOLEAN),
        ("Directory", wintypes.BOOLEAN),
    ]


class _FileIdBothDirectoryInfo(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", wintypes.DWORD),
        ("FileIndex", wintypes.DWORD),
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("AllocationSize", ctypes.c_longlong),
        ("FileAttributes", wintypes.DWORD),
        ("FileNameLength", wintypes.DWORD),
        ("EaSize", wintypes.DWORD),
        ("ShortNameLength", ctypes.c_byte),
        ("ShortName", wintypes.WCHAR * 12),
        ("FileId", ctypes.c_longlong),
        ("FileName", wintypes.WCHAR * 1),
    ]


class _FileRenameInformationEx(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD),
        ("FileName", wintypes.WCHAR * 1),
    ]


class _FileDispositionInformation(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOLEAN)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.DuplicateHandle.argtypes = [
    wintypes.HANDLE,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
_kernel32.DuplicateHandle.restype = wintypes.BOOL
_kernel32.GetFileInformationByHandleEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
]
_kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
_kernel32.GetVolumeInformationByHandleW.argtypes = [
    wintypes.HANDLE,
    wintypes.LPWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR,
    wintypes.DWORD,
]
_kernel32.GetVolumeInformationByHandleW.restype = wintypes.BOOL
_kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetDriveTypeW.restype = wintypes.UINT
_kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
_kernel32.ReadFile.restype = wintypes.BOOL
_kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
_kernel32.WriteFile.restype = wintypes.BOOL
_kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
_kernel32.FlushFileBuffers.restype = wintypes.BOOL

_ntdll.NtCreateFile.argtypes = [
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.DWORD,
    ctypes.POINTER(_ObjectAttributes),
    ctypes.POINTER(_IoStatusBlock),
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_ntdll.NtCreateFile.restype = ctypes.c_long
_ntdll.NtSetInformationFile.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(_IoStatusBlock),
    wintypes.LPVOID,
    wintypes.ULONG,
    ctypes.c_int,
]
_ntdll.NtSetInformationFile.restype = ctypes.c_long
_ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
_ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG

_REQUIRED_APIS = (
    _kernel32.CreateFileW,
    _kernel32.GetFileInformationByHandleEx,
    _kernel32.GetVolumeInformationByHandleW,
    _kernel32.GetDriveTypeW,
    _kernel32.ReadFile,
    _kernel32.WriteFile,
    _kernel32.FlushFileBuffers,
    _ntdll.NtCreateFile,
    _ntdll.NtSetInformationFile,
    _ntdll.RtlNtStatusToDosError,
)


def _raise_last_error() -> None:
    raise ctypes.WinError(ctypes.get_last_error())


def _raise_ntstatus(status: int, name: str) -> None:
    code = int(_ntdll.RtlNtStatusToDosError(status))
    if code in {2, 3}:
        raise FileNotFoundError(code, os.strerror(code), name)
    if code in {5, 32}:
        raise PermissionError(code, os.strerror(code), name)
    if code in {80, 183}:
        raise FileExistsError(code, os.strerror(code), name)
    raise OSError(code, ctypes.FormatError(code), name)


class WindowsFilesystemError(OSError):
    """The workspace cannot satisfy the Windows dashboard security contract."""


def _require_windows_apis() -> None:
    if not all(callable(api) for api in _REQUIRED_APIS):
        raise WindowsFilesystemError(
            "required Windows filesystem APIs are unavailable"
        )


class _Handle:
    def __init__(self, value: int | None) -> None:
        if value in {None, 0, INVALID_HANDLE_VALUE}:
            raise ValueError("invalid Windows handle")
        self.value = int(value)

    def close(self) -> None:
        if self.value:
            _kernel32.CloseHandle(wintypes.HANDLE(self.value))
            self.value = 0

    def duplicate(self) -> _Handle:
        process = _kernel32.GetCurrentProcess()
        result = wintypes.HANDLE()
        if not _kernel32.DuplicateHandle(
            process,
            wintypes.HANDLE(self.value),
            process,
            ctypes.byref(result),
            0,
            False,
            0x00000002,
        ):
            _raise_last_error()
        return _Handle(result.value)

    def detach_fd(self, flags: int) -> int:
        value = self.value
        self.value = 0
        try:
            return msvcrt.open_osfhandle(value, flags)
        except Exception:
            _kernel32.CloseHandle(wintypes.HANDLE(value))
            raise

    def __enter__(self) -> _Handle:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


class WindowsEntry(NamedTuple):
    name: str
    kind: str
    size: int
    reparse: bool


def _attribute_info(handle: _Handle) -> _FileAttributeTagInfo:
    info = _FileAttributeTagInfo()
    if not _kernel32.GetFileInformationByHandleEx(
        wintypes.HANDLE(handle.value),
        FILE_ATTRIBUTE_TAG_INFO_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        _raise_last_error()
    return info


def _standard_info(handle: _Handle) -> _FileStandardInfo:
    info = _FileStandardInfo()
    if not _kernel32.GetFileInformationByHandleEx(
        wintypes.HANDLE(handle.value),
        FILE_STANDARD_INFO_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        _raise_last_error()
    return info


def _validate_handle(handle: _Handle, *, directory: bool, label: str) -> None:
    attributes = _attribute_info(handle).FileAttributes
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        raise WindowsFilesystemError(f"reparse points are unsupported: {label}")
    actual_directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
    if actual_directory != directory:
        expected = "directory" if directory else "regular file"
        raise WindowsFilesystemError(f"expected {expected}: {label}")


def _drive_type(root: str) -> int:
    return int(_kernel32.GetDriveTypeW(root))


def _volume_filesystem(handle: _Handle) -> str:
    filesystem = ctypes.create_unicode_buffer(64)
    if not _kernel32.GetVolumeInformationByHandleW(
        wintypes.HANDLE(handle.value),
        None,
        0,
        None,
        None,
        None,
        filesystem,
        len(filesystem),
    ):
        _raise_last_error()
    return filesystem.value


def _nt_open(
    parent: _Handle,
    name: str,
    *,
    directory: bool,
    disposition: int = FILE_OPEN,
    access: int | None = None,
    share: int = FILE_SHARE_ALL,
) -> _Handle:
    if not name or "\\" in name or "/" in name or "\x00" in name:
        raise ValueError(f"invalid handle-relative name: {name!r}")
    encoded = name.encode("utf-16-le")
    buffer = ctypes.create_unicode_buffer(name)
    unicode_name = _UnicodeString(
        len(encoded), len(encoded) + 2, ctypes.cast(buffer, wintypes.LPWSTR)
    )
    attributes = _ObjectAttributes(
        ctypes.sizeof(_ObjectAttributes),
        wintypes.HANDLE(parent.value),
        ctypes.pointer(unicode_name),
        OBJ_CASE_INSENSITIVE,
        None,
        None,
    )
    status_block = _IoStatusBlock()
    result = wintypes.HANDLE()
    desired_access = access
    if desired_access is None:
        desired_access = (
            FILE_LIST_DIRECTORY if directory else FILE_READ_DATA
        ) | FILE_READ_ATTRIBUTES | SYNCHRONIZE
    options = (
        FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE
    ) | FILE_SYNCHRONOUS_IO_NONALERT | FILE_OPEN_REPARSE_POINT
    status = _ntdll.NtCreateFile(
        ctypes.byref(result),
        desired_access,
        ctypes.byref(attributes),
        ctypes.byref(status_block),
        None,
        FILE_ATTRIBUTE_NORMAL,
        share,
        disposition,
        options,
        None,
        0,
    )
    if status < 0:
        _raise_ntstatus(status, name)
    handle = _Handle(result.value)
    try:
        _validate_handle(handle, directory=directory, label=name)
    except Exception:
        handle.close()
        raise
    return handle


def _open_drive_root(path: Path) -> _Handle:
    drive = path.drive
    if not re.fullmatch(r"[A-Za-z]:", drive):
        raise WindowsFilesystemError(
            "Windows dashboard workspaces must use a local drive-letter path"
        )
    root = f"{drive}\\"
    handle = _kernel32.CreateFileW(
        root,
        FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        _raise_last_error()
    result = _Handle(handle)
    try:
        _validate_handle(result, directory=True, label=root)
        if _drive_type(root) != DRIVE_FIXED:
            raise WindowsFilesystemError(
                "Windows dashboard workspaces must be on a fixed local drive"
            )
        filesystem = _volume_filesystem(result)
        if filesystem.casefold() != "ntfs":
            raise WindowsFilesystemError(
                f"Windows dashboard workspaces require NTFS, found {filesystem or 'unknown'}"
            )
    except Exception:
        result.close()
        raise
    return result


class WindowsDirectory:
    """A directory tree rooted at a handle that never follows reparse points."""

    def __init__(self, handle: _Handle, display_path: Path) -> None:
        self._handle = handle
        self.display_path = display_path

    @classmethod
    def open_workspace(cls, path: Path) -> WindowsDirectory:
        _require_windows_apis()
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise WindowsFilesystemError(
                "Windows dashboard support currently requires 64-bit Python"
            )
        raw = str(path.expanduser())
        if raw.startswith(("\\\\", "\\?\\", "\\.\\")):
            raise WindowsFilesystemError(
                "Windows dashboard workspaces must use a normal drive-letter path"
            )
        absolute = Path(os.path.abspath(raw))
        current = _open_drive_root(absolute)
        try:
            relative_parts = absolute.parts[1:]
            for part in relative_parts:
                child = _nt_open(current, part, directory=True)
                current.close()
                current = child
            return cls(current, absolute)
        except Exception:
            current.close()
            raise

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> WindowsDirectory:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _parts(self, relative: str | PurePosixPath) -> tuple[str, ...]:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".."} for part in pure.parts):
            raise ValueError(f"unsafe relative path: {relative}")
        return tuple(part for part in pure.parts if part != ".")

    def open_subtree(self, relative: str | PurePosixPath) -> WindowsDirectory:
        current = self._handle.duplicate()
        try:
            for part in self._parts(relative):
                child = _nt_open(current, part, directory=True)
                current.close()
                current = child
            display = self.display_path.joinpath(*self._parts(relative))
            return WindowsDirectory(current, display)
        except Exception:
            current.close()
            raise

    def _open_parent(
        self, relative: str | PurePosixPath, *, create: bool = False
    ) -> tuple[_Handle, str]:
        parts = self._parts(relative)
        if not parts:
            raise ValueError("relative file path is empty")
        current = self._handle.duplicate()
        try:
            for part in parts[:-1]:
                child = _nt_open(
                    current,
                    part,
                    directory=True,
                    disposition=FILE_OPEN_IF if create else FILE_OPEN,
                )
                current.close()
                current = child
            return current, parts[-1]
        except Exception:
            current.close()
            raise

    def scan(self, relative: str | PurePosixPath = ".") -> list[WindowsEntry]:
        with self.open_subtree(relative) as directory:
            buffer = ctypes.create_string_buffer(64 * 1024)
            entries: list[WindowsEntry] = []
            first = True
            while True:
                ctypes.set_last_error(0)
                if not _kernel32.GetFileInformationByHandleEx(
                    wintypes.HANDLE(directory._handle.value),
                    FILE_ID_BOTH_DIRECTORY_RESTART_INFO_CLASS
                    if first
                    else FILE_ID_BOTH_DIRECTORY_INFO_CLASS,
                    buffer,
                    ctypes.sizeof(buffer),
                ):
                    error = ctypes.get_last_error()
                    if error == ERROR_NO_MORE_FILES:
                        break
                    raise ctypes.WinError(error)
                first = False
                offset = 0
                while True:
                    info = _FileIdBothDirectoryInfo.from_buffer(buffer, offset)
                    name = ctypes.wstring_at(
                        ctypes.addressof(buffer)
                        + offset
                        + _FileIdBothDirectoryInfo.FileName.offset,
                        info.FileNameLength // 2,
                    )
                    if name not in {".", ".."}:
                        attributes = int(info.FileAttributes)
                        kind = (
                            "directory"
                            if attributes & FILE_ATTRIBUTE_DIRECTORY
                            else "file"
                        )
                        entries.append(
                            WindowsEntry(
                                name=name,
                                kind=kind,
                                size=max(0, int(info.EndOfFile)),
                                reparse=bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT),
                            )
                        )
                    if info.NextEntryOffset == 0:
                        break
                    offset += int(info.NextEntryOffset)
            return entries

    def _open_regular_handle(
        self,
        relative: str | PurePosixPath,
        *,
        access: int | None = None,
        disposition: int = FILE_OPEN,
        create_parent: bool = False,
    ) -> _Handle:
        parent, name = self._open_parent(relative, create=create_parent)
        try:
            return _nt_open(
                parent,
                name,
                directory=False,
                access=access,
                disposition=disposition,
            )
        finally:
            parent.close()

    @staticmethod
    def _read_handle(handle: _Handle, limit: int | None = None) -> bytes:
        try:
            size = int(_standard_info(handle).EndOfFile)
            if limit is not None and size > limit:
                raise ValueError("file exceeds configured limit")
            fd = handle.detach_fd(os.O_RDONLY | os.O_BINARY)
            with os.fdopen(fd, "rb") as stream:
                data = stream.read(None if limit is None else limit + 1)
            if limit is not None and len(data) > limit:
                raise ValueError("file exceeds configured limit")
            return data
        finally:
            handle.close()

    @classmethod
    def _read_from_parent(
        cls, parent: _Handle, name: str, limit: int | None = None
    ) -> bytes:
        handle = _nt_open(parent, name, directory=False)
        return cls._read_handle(handle, limit)

    def read_regular(
        self, relative: str | PurePosixPath, *, limit: int | None = None
    ) -> bytes:
        handle = self._open_regular_handle(relative)
        return self._read_handle(handle, limit)

    def open_regular(
        self, relative: str | PurePosixPath, *, limit: int | None = None
    ) -> tuple[BinaryIO, int]:
        handle = self._open_regular_handle(relative)
        try:
            size = int(_standard_info(handle).EndOfFile)
            if limit is not None and size > limit:
                raise ValueError("file exceeds configured limit")
            fd = handle.detach_fd(os.O_RDONLY | os.O_BINARY)
            return os.fdopen(fd, "rb"), size
        except Exception:
            handle.close()
            raise

    @staticmethod
    def _write_handle(handle: _Handle, content: bytes) -> None:
        offset = 0
        while offset < len(content):
            chunk = content[offset : offset + 1024 * 1024]
            buffer = ctypes.create_string_buffer(chunk)
            written = wintypes.DWORD()
            if not _kernel32.WriteFile(
                wintypes.HANDLE(handle.value),
                buffer,
                len(chunk),
                ctypes.byref(written),
                None,
            ):
                _raise_last_error()
            if written.value <= 0:
                raise OSError("Windows write made no progress")
            offset += int(written.value)
        if not _kernel32.FlushFileBuffers(wintypes.HANDLE(handle.value)):
            _raise_last_error()

    @staticmethod
    def _mark_delete(handle: _Handle) -> None:
        information = _FileDispositionInformation(True)
        status_block = _IoStatusBlock()
        status = _ntdll.NtSetInformationFile(
            wintypes.HANDLE(handle.value),
            ctypes.byref(status_block),
            ctypes.byref(information),
            ctypes.sizeof(information),
            FILE_DISPOSITION_INFORMATION_CLASS,
        )
        if status < 0:
            _raise_ntstatus(status, "temporary file")

    @staticmethod
    def _rename_replace(handle: _Handle, parent: _Handle, name: str) -> None:
        encoded = name.encode("utf-16-le")
        size = max(
            ctypes.sizeof(_FileRenameInformationEx),
            _FileRenameInformationEx.FileName.offset + len(encoded),
        )
        buffer = ctypes.create_string_buffer(size)
        information = _FileRenameInformationEx.from_buffer(buffer)
        information.Flags = (
            FILE_RENAME_REPLACE_IF_EXISTS | FILE_RENAME_POSIX_SEMANTICS
        )
        information.RootDirectory = wintypes.HANDLE(parent.value)
        information.FileNameLength = len(encoded)
        ctypes.memmove(
            ctypes.addressof(buffer) + _FileRenameInformationEx.FileName.offset,
            encoded,
            len(encoded),
        )
        status_block = _IoStatusBlock()
        status = _ntdll.NtSetInformationFile(
            wintypes.HANDLE(handle.value),
            ctypes.byref(status_block),
            buffer,
            size,
            FILE_RENAME_INFORMATION_EX_CLASS,
        )
        if status < 0:
            _raise_ntstatus(status, name)

    def replace_regular(
        self,
        relative: str | PurePosixPath,
        content: bytes,
        expected_hash: str,
    ) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            raise ValueError("expected hash must be a SHA-256 digest")
        parent, name = self._open_parent(relative)
        guard: _Handle | None = None
        guard_stream: BinaryIO | None = None
        guard_locked = False
        temporary: _Handle | None = None
        renamed = False
        verification = b""
        try:
            try:
                guard = _nt_open(
                    parent,
                    name,
                    directory=False,
                    access=FILE_READ_DATA
                    | FILE_WRITE_DATA
                    | FILE_READ_ATTRIBUTES
                    | SYNCHRONIZE,
                    share=FILE_SHARE_READ | FILE_SHARE_DELETE,
                )
                guard_fd = guard.detach_fd(os.O_RDWR | os.O_BINARY)
                guard_stream = os.fdopen(guard_fd, "r+b", buffering=0)
                guard_stream.seek(0)
                msvcrt.locking(guard_stream.fileno(), msvcrt.LK_NBLCK, 1)
                guard_locked = True
            except OSError as exc:
                code = getattr(exc, "winerror", None) or exc.errno
                if code in {13, 32, 33}:
                    raise FileExistsError(
                        "file is being modified by another process"
                    ) from exc
                raise
            assert guard_stream is not None
            guard_stream.seek(0)
            current = guard_stream.read()
            if hashlib.sha256(current).hexdigest() != expected_hash:
                raise FileExistsError("file changed since it was opened")
            for _ in range(8):
                temporary_name = f".sd-{uuid.uuid4().hex}.tmp"
                try:
                    temporary = _nt_open(
                        parent,
                        temporary_name,
                        directory=False,
                        disposition=FILE_CREATE,
                        access=FILE_WRITE_DATA
                        | FILE_READ_ATTRIBUTES
                        | DELETE
                        | SYNCHRONIZE,
                    )
                    break
                except FileExistsError:
                    continue
            if temporary is None:
                raise FileExistsError("cannot allocate a temporary file")
            self._write_handle(temporary, content)
            guard_stream.seek(0)
            latest = guard_stream.read()
            if hashlib.sha256(latest).hexdigest() != expected_hash:
                raise FileExistsError("file changed since it was opened")
            self._rename_replace(temporary, parent, name)
            renamed = True
            verification = self._read_from_parent(parent, name)
        finally:
            if temporary is not None:
                if not renamed:
                    with contextlib.suppress(OSError):
                        self._mark_delete(temporary)
                temporary.close()
            if guard_stream is not None:
                if guard_locked:
                    with contextlib.suppress(OSError):
                        guard_stream.seek(0)
                        msvcrt.locking(
                            guard_stream.fileno(), msvcrt.LK_UNLCK, 1
                        )
                guard_stream.close()
            elif guard is not None:
                guard.close()
            parent.close()
        digest = hashlib.sha256(content).hexdigest()
        if hashlib.sha256(verification).hexdigest() != digest:
            raise OSError("replaced file does not match the submitted content")
        return digest

    @contextlib.contextmanager
    def transaction_lock(self) -> Iterator[None]:
        operational = self.open_subtree(".")
        lock_handle: _Handle | None = None
        try:
            for part in (".short-drama", "locks"):
                child = _nt_open(
                    operational._handle,
                    part,
                    directory=True,
                    disposition=FILE_OPEN_IF,
                )
                operational.close()
                operational = WindowsDirectory(
                    child, operational.display_path / part
                )
            lock_handle = _nt_open(
                operational._handle,
                "transaction.lock",
                directory=False,
                disposition=FILE_OPEN_IF,
                access=FILE_READ_DATA
                | FILE_WRITE_DATA
                | FILE_READ_ATTRIBUTES
                | SYNCHRONIZE,
            )
            fd = lock_handle.detach_fd(os.O_RDWR | os.O_BINARY)
            with os.fdopen(fd, "r+b", buffering=0) as stream:
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                    os.fsync(stream.fileno())
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            if lock_handle is not None:
                lock_handle.close()
            operational.close()
