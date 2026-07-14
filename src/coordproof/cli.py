"""Installable command-line boundaries for CoordProof projects."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO

from . import __version__

EVIDENCE_FILENAMES = (
    "project.normalized.json",
    "project-summary.json",
    "project.ifc",
    "ifc-entity-summary.md",
    "openbim-semantic-inventory.csv",
)
MANIFEST_FILENAME = "build-manifest.json"
EVIDENCE_PACKAGE_FILENAMES = frozenset((*EVIDENCE_FILENAMES, MANIFEST_FILENAME))
_SECURE_PUBLICATION_SUPPORTED = (
    os.name == "posix"
    and all(
        function in os.supports_dir_fd
        for function in (os.open, os.mkdir, os.rename, os.stat, os.unlink)
    )
    and os.listdir in os.supports_fd
    and os.stat in os.supports_follow_symlinks
    and all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW"))
)


class CLIError(RuntimeError):
    """A user-facing command failure that does not need a traceback."""


class ProjectValidationError(CLIError):
    """A ProjectSpec validation failure, reported with the validation exit code."""


def _tools_directory() -> Path:
    """Locate bundled legacy modules without depending on the process CWD."""

    source_tools = Path(__file__).resolve().parents[2] / "tools"
    if source_tools.is_dir():
        return source_tools

    try:
        installed = distribution("coordproof-openbim-mep")
    except PackageNotFoundError as exc:
        raise CLIError("the installed CoordProof tools package is incomplete") from exc
    for entry in installed.files or ():
        if entry.as_posix() in {"project_spec.py", "tools/project_spec.py"}:
            return Path(installed.locate_file(entry)).resolve().parent
    raise CLIError("the installed CoordProof tools package is incomplete")


def _legacy_module(name: str) -> ModuleType:
    tools_directory = _tools_directory().resolve()
    tools_string = str(tools_directory)
    if tools_string not in sys.path:
        sys.path.insert(0, tools_string)
    module = importlib.import_module(name)
    module_path = Path(module.__file__ or "").resolve()
    if module_path.parent != tools_directory:
        raise CLIError(f"cannot load bundled module {name!r}; another module shadows it")
    return module


def _project_spec_module() -> ModuleType:
    module = _legacy_module("project_spec")
    bundled_spec = Path(module.__file__ or "").resolve().parent / "spec"
    bundled_project = bundled_spec / "mechanical_room.project.json"
    bundled_schema = bundled_spec / "project.schema.json"
    if bundled_project.is_file() and not getattr(module, "_coordproof_bundled_paths", False):
        original_loader = module.load_project_spec

        def load_project_spec(path: str | Path = bundled_project) -> Any:
            return original_loader(path)

        module.DEFAULT_PROJECT_SPEC_PATH = bundled_project
        module.PROJECT_SPEC_SCHEMA_PATH = bundled_schema
        module.load_project_spec = load_project_spec
        module._coordproof_bundled_paths = True
    return module


def _load_project(path: Path) -> Any:
    module = _project_spec_module()
    try:
        return module.load_project_spec(path)
    except module.ProjectSpecError as exc:
        raise ProjectValidationError(str(exc)) from exc


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_schema_id() -> str:
    module = _project_spec_module()
    try:
        schema = json.loads(module.PROJECT_SPEC_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (AttributeError, OSError, TypeError, json.JSONDecodeError) as exc:
        raise CLIError("the bundled ProjectSpec schema is unreadable") from exc
    schema_id = schema.get("$id") if isinstance(schema, dict) else None
    if not isinstance(schema_id, str) or not schema_id.startswith("https://"):
        raise CLIError("the bundled ProjectSpec schema has no stable HTTPS identifier")
    return schema_id


def _validate_ifc_model(model: Any) -> None:
    """Fail publication when the generated IFC violates its EXPRESS contract."""

    import ifcopenshell.validate

    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger, express_rules=True)
    errors = [statement for statement in logger.statements if statement.get("level") == "error"]
    if not errors:
        return
    first_line = str(errors[0].get("message", "validation error")).splitlines()[0]
    raise CLIError(
        f"generated IFC failed formal validation with {len(errors)} error(s): {first_line}"
    )


def _project_snapshot(project_path: Path) -> tuple[Any, object]:
    """Validate one immutable source snapshot and return its model and JSON value."""

    source = project_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="coordproof-project-") as temporary_directory:
        snapshot = Path(temporary_directory) / project_path.name
        snapshot.write_bytes(source)
        try:
            project = _load_project(snapshot)
        except ProjectValidationError as exc:
            message = str(exc).replace(str(snapshot), str(project_path))
            raise ProjectValidationError(message) from exc

    # Keep diagnostics and project-scoped canonical identity tied to the selected
    # path while every generated value continues to come from the frozen bytes.
    project = replace(project, source_path=project_path)
    normalized_payload = json.loads(source.decode("utf-8"))
    normalized_payload["$schema"] = _project_schema_id()
    return project, normalized_payload


def _manifest(project: Any, stage: Path) -> dict[str, object]:
    artifacts = []
    for filename in sorted(EVIDENCE_FILENAMES):
        path = stage / filename
        artifacts.append(
            {
                "path": filename,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "artifacts": artifacts,
        "format_version": 1,
        "generator": {"name": "coordproof", "version": __version__},
        "profile": "evidence",
        "project_id": project.project.project_id,
        "schema_version": project.schema_version,
    }


def _absolute_lexical_path(path: Path) -> Path:
    """Return an absolute path without resolving filesystem links."""

    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path) -> None:
    """Reject every existing symlink in a publication path."""

    absolute = _absolute_lexical_path(path)
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & reparse_point:
            raise CLIError(
                f"refusing to publish through a symlinked path component: {current}"
            )


def _preflight_evidence_output(output: Path) -> None:
    _reject_symlink_components(output)
    if output.exists() and not output.is_dir():
        raise CLIError(f"evidence output is not a directory: {output}")
    if not output.exists():
        return

    unexpected = sorted(
        entry.name for entry in output.iterdir() if entry.name not in EVIDENCE_PACKAGE_FILENAMES
    )
    if unexpected:
        names = ", ".join(unexpected)
        raise CLIError(
            "evidence output must be a dedicated directory; "
            f"unexpected existing entries: {names}"
        )
    for filename in EVIDENCE_PACKAGE_FILENAMES:
        destination = output / filename
        if destination.is_symlink():
            raise CLIError(f"refusing to replace a symlinked output: {destination}")
        if destination.exists() and not destination.is_file():
            raise CLIError(f"refusing to replace a non-file output: {destination}")


def _secure_publication_supported() -> bool:
    return _SECURE_PUBLICATION_SUPPORTED


def _open_pinned_output_directory(output: Path) -> int:
    """Securely create and open *output* without following path components."""

    if not _secure_publication_supported():
        raise CLIError(
            "secure evidence publication requires POSIX directory-handle support; "
            "this platform is not yet certified for evidence builds"
        )

    absolute = _absolute_lexical_path(output)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    current_fd = os.open(absolute.anchor, flags)
    current_path = Path(absolute.anchor)
    try:
        for component in absolute.parts[1:]:
            current_path /= component
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except FileNotFoundError:
                os.mkdir(component, mode=0o755, dir_fd=current_fd)
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError as exc:
                raise CLIError(
                    "refusing to publish through a non-directory or linked path "
                    f"component: {current_path}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _preflight_pinned_output(
    output_fd: int,
    output: Path,
    ignored: set[str] | None = None,
) -> None:
    """Validate an already pinned output directory without reopening its path."""

    ignored_names = ignored or set()
    entries = set(os.listdir(output_fd))
    unexpected = sorted(entries - EVIDENCE_PACKAGE_FILENAMES - ignored_names)
    if unexpected:
        names = ", ".join(unexpected)
        raise CLIError(
            "evidence output must be a dedicated directory; "
            f"unexpected existing entries: {names}"
        )
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for filename in EVIDENCE_PACKAGE_FILENAMES & entries:
        metadata = os.stat(filename, dir_fd=output_fd, follow_symlinks=False)
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & reparse_point:
            raise CLIError(f"refusing to replace a symlinked output: {output / filename}")
        if not stat.S_ISREG(metadata.st_mode):
            raise CLIError(f"refusing to replace a non-file output: {output / filename}")


def _copy_to_pinned_temporary(stage_file: Path, output_fd: int) -> str:
    """Copy one staged file to an unpredictable leaf in a pinned directory."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    while True:
        temporary_name = f".coordproof-publish-{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(temporary_name, flags, 0o666, dir_fd=output_fd)
        except FileExistsError:
            continue
        break
    completed = False
    try:
        with stage_file.open("rb") as source, os.fdopen(descriptor, "wb") as destination:
            descriptor = -1
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        completed = True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completed:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=output_fd)
    return temporary_name


def _publish(stage: Path, output: Path) -> None:
    _preflight_evidence_output(output)
    output_fd = _open_pinned_output_directory(output)
    temporary_names: dict[str, str] = {}
    try:
        _preflight_pinned_output(output_fd, output)
        for filename in (*EVIDENCE_FILENAMES, MANIFEST_FILENAME):
            temporary_names[filename] = _copy_to_pinned_temporary(
                stage / filename,
                output_fd,
            )

        # A concurrent ancestor rename cannot redirect any operation below:
        # every mutation is relative to the verified directory handle. Recheck
        # its contents before invalidating the previous certificate.
        _preflight_pinned_output(output_fd, output, set(temporary_names.values()))
        with suppress(FileNotFoundError):
            os.unlink(MANIFEST_FILENAME, dir_fd=output_fd)
        for filename in EVIDENCE_FILENAMES:
            temporary_name = temporary_names[filename]
            os.rename(
                temporary_name,
                filename,
                src_dir_fd=output_fd,
                dst_dir_fd=output_fd,
            )
            del temporary_names[filename]
        os.fsync(output_fd)
        manifest_temporary = temporary_names[MANIFEST_FILENAME]
        _preflight_pinned_output(output_fd, output, {manifest_temporary})
        os.rename(
            manifest_temporary,
            MANIFEST_FILENAME,
            src_dir_fd=output_fd,
            dst_dir_fd=output_fd,
        )
        del temporary_names[MANIFEST_FILENAME]
        os.fsync(output_fd)
    finally:
        try:
            for temporary_name in temporary_names.values():
                with suppress(FileNotFoundError):
                    os.unlink(temporary_name, dir_fd=output_fd)
        finally:
            os.close(output_fd)


def build_evidence(project_path: Path, output: Path | None = None) -> Path:
    project_path = project_path.expanduser().resolve()
    project, normalized_payload = _project_snapshot(project_path)
    selected_output = output if output is not None else _default_output(project)
    lexical_output = _absolute_lexical_path(selected_output.expanduser())
    _reject_symlink_components(lexical_output)
    resolved_output = lexical_output.resolve()
    if resolved_output == project_path or project_path.is_relative_to(resolved_output):
        raise CLIError("the build output cannot contain the source ProjectSpec")

    _preflight_evidence_output(lexical_output)
    with tempfile.TemporaryDirectory(
        prefix=".coordproof-stage-",
    ) as temporary_directory:
        stage = Path(temporary_directory)
        _write_json(stage / "project.normalized.json", normalized_payload)
        _write_json(stage / "project-summary.json", project.summary())

        openbim_core = _legacy_module("openbim_core")
        model = openbim_core.build_openbim_model(project)
        _validate_ifc_model(model)
        openbim_core.write_openbim_outputs(
            model,
            ifc_path=stage / "project.ifc",
            summary_path=stage / "ifc-entity-summary.md",
            inventory_path=stage / "openbim-semantic-inventory.csv",
            project_spec=project,
            patch_bim_map=False,
            ifc_display_path="project.ifc",
            project_source_label="project.normalized.json",
        )
        _write_json(stage / MANIFEST_FILENAME, _manifest(project, stage))
        _publish(stage, lexical_output)
    return resolved_output


def _canonical_checkout(project_path: Path) -> Path | None:
    # Never discover an executable build script relative to user input. Source
    # checkouts may run the native profiles; installed wheels intentionally do
    # not ship or execute an adjacent arbitrary tools/build_all.py.
    root = _tools_directory().parent.resolve()
    expected = (root / "spec" / "mechanical_room.project.json").resolve()
    build_script = root / "tools" / "build_all.py"
    if project_path.resolve() == expected and build_script.is_file():
        return root
    return None


def build_canonical(project_path: Path, profile: str) -> int:
    root = _canonical_checkout(project_path)
    if root is None:
        raise CLIError(
            f"the {profile!r} profile is tied to the canonical CoordProof checkout; "
            "use the 'evidence' profile for a supported noncanonical ProjectSpec"
        )
    command = [sys.executable, str(root / "tools" / "build_all.py"), "--profile", profile]
    return subprocess.run(command, cwd=root, check=False).returncode


def _default_output(project: Any) -> Path:
    return Path.cwd() / "build" / project.project.project_id


def _validate(project_path: Path, stdout: TextIO) -> int:
    project = _load_project(project_path)
    summary = project.summary()
    print(f"ProjectSpec valid: {project.source_path}", file=stdout)
    print(
        f"- {summary['asset_type_count']} asset types, {summary['occurrence_count']} "
        f"occurrences, {summary['artifact_count']} artifacts",
        file=stdout,
    )
    print(
        f"- {summary['system_count']} systems, {summary['connection_count']} connections, "
        f"{summary['declared_port_count']} declared ports",
        file=stdout,
    )
    return 0


def _summary(project_path: Path, stdout: TextIO) -> int:
    print(json.dumps(_load_project(project_path).summary(), indent=2, sort_keys=True), file=stdout)
    return 0


def _build(args: argparse.Namespace, stdout: TextIO) -> int:
    project_path = args.project.expanduser().resolve()
    if args.profile in {"core", "full"}:
        if args.output is not None:
            raise CLIError("--output is only supported by the 'evidence' profile")
        return build_canonical(project_path, args.profile)

    output = build_evidence(project_path, args.output)
    print(f"Built evidence package: {output}", file=stdout)
    return 0


def _clash(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    module = _legacy_module("external_ifc_clash")
    try:
        module.preflight_output_paths(args.output, args.bcf)
        if args.bcf and not module.bcf_available():
            raise module.ClashCapabilityError(
                "BCF output requires the optional 'bcf' extra with bcf-client 0.8.x"
            )
        config = module.ClashConfig(
            mode=args.mode,
            a_label=args.a_label,
            b_label=args.b_label,
            a_classes=tuple(args.a_classes or ("IfcElement",)),
            b_classes=tuple(args.b_classes or ("IfcElement",)),
            tolerance_mm=args.tolerance_mm,
            clearance_mm=args.clearance_mm,
            allow_touching=args.allow_touching,
        )
        limits = module.ClashLimits(
            max_file_bytes=args.max_file_bytes,
            max_elements_per_side=args.max_elements_per_side,
            max_triangles_per_side=args.max_triangles_per_side,
            max_candidate_pairs=args.max_candidate_pairs,
            max_results=args.max_results,
            workers=args.workers,
        )
        report = module.run_external_clash(
            args.a_ifc,
            args.b_ifc,
            config=config,
            limits=limits,
        )
        module.write_reports(report, args.output, args.bcf)
    except module.ClashError as exc:
        print(f"coordproof clash: {exc}", file=stderr)
        return 2

    count = report["summary"]["clash_count"]
    print(f"External IFC clash complete: {count} clash(es); wrote {args.output}", file=stdout)
    return 1 if args.fail_on_clash and count else 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coordproof",
        description="Validate and build deterministic CoordProof ProjectSpec evidence.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate_parser = commands.add_parser("validate", help="validate a ProjectSpec")
    validate_parser.add_argument("project", type=Path, help="path to a ProjectSpec JSON file")

    summary_parser = commands.add_parser("summary", help="print a ProjectSpec inventory summary")
    summary_parser.add_argument("project", type=Path, help="path to a ProjectSpec JSON file")

    build_parser = commands.add_parser("build", help="build evidence for a ProjectSpec")
    build_parser.add_argument("project", type=Path, help="path to a ProjectSpec JSON file")
    build_parser.add_argument(
        "--profile",
        choices=("evidence", "core", "full"),
        default="evidence",
        help=(
            "evidence builds a portable IFC bundle for a supported ProjectSpec v1 contract; "
            "core/full run the checkout's canonical multi-tool pipeline"
        ),
    )
    build_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="evidence output directory (default: ./build/<project-id>)",
    )

    clash_parser = commands.add_parser(
        "clash",
        help="run a bounded clash set across two external IFC models",
    )
    clash_parser.add_argument("a_ifc", type=Path, help="side A uncompressed IFC file")
    clash_parser.add_argument("b_ifc", type=Path, help="side B uncompressed IFC file")
    clash_parser.add_argument("-o", "--output", type=Path, required=True)
    clash_parser.add_argument("--bcf", type=Path, help="optional BCF 3.0 issue package")
    clash_parser.add_argument("--a-label", default="A")
    clash_parser.add_argument("--b-label", default="B")
    clash_parser.add_argument(
        "--mode",
        choices=("collision", "intersection", "clearance"),
        default="collision",
    )
    clash_parser.add_argument("--a-class", action="append", dest="a_classes")
    clash_parser.add_argument("--b-class", action="append", dest="b_classes")
    clash_parser.add_argument("--tolerance-mm", type=float, default=2.0)
    clash_parser.add_argument("--clearance-mm", type=float, default=50.0)
    clash_parser.add_argument("--allow-touching", action="store_true")
    clash_parser.add_argument("--max-file-bytes", type=int, default=256 * 1024 * 1024)
    clash_parser.add_argument("--max-elements-per-side", type=int, default=5_000)
    clash_parser.add_argument("--max-triangles-per-side", type=int, default=5_000_000)
    clash_parser.add_argument("--max-candidate-pairs", type=int, default=10_000_000)
    clash_parser.add_argument("--max-results", type=int, default=10_000)
    clash_parser.add_argument("--workers", type=int, default=1)
    clash_parser.add_argument("--fail-on-clash", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    args = create_parser().parse_args(argv)
    try:
        if args.command == "clash":
            return _clash(args, output, errors)
        project_path = args.project.expanduser().resolve()
        if args.command == "validate":
            return _validate(project_path, output)
        if args.command == "summary":
            return _summary(project_path, output)
        return _build(args, output)
    except ProjectValidationError as exc:
        print(exc, file=errors)
        return 2
    except (CLIError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"coordproof: {exc}", file=errors)
        return 1
