#!/usr/bin/env python3
"""
Macro Sign Service CLI Tool
Command-line tool for signing VBA macros locally and via the service API.

Usage:
    python -m cli.macro_sign_cli sign <file> [--profile NAME] [--algorithm sha256]
    python -m cli.macro_sign_cli sign-vba <file.xlsm> [--output signed.xlsm]
    python -m cli.macro_sign_cli verify <file> --signature <hex>
    python -m cli.macro_sign_cli status <job_id>
    python -m cli.macro_sign_cli health
    python -m cli.macro_sign_cli generate-cert [--name "Dev Cert"] [--days 365]
    python -m cli.macro_sign_cli generate-pfx [--name "Dev Cert"] [--days 365]
    python -m cli.macro_sign_cli cert-info [--cert-dir ./certs]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


def get_base_url() -> str:
    return os.environ.get("MACRO_SIGN_URL", "http://localhost:8000")


def get_api_key() -> Optional[str]:
    return os.environ.get("MACRO_SIGN_API_KEY")


def get_headers() -> dict:
    headers = {"Accept": "application/json"}
    api_key = get_api_key()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def print_json(data: dict, indent: int = 2) -> None:
    """Pretty print JSON data."""
    print(json.dumps(data, indent=indent, default=str))


def cmd_sign(args: argparse.Namespace) -> int:
    """Sign a macro file."""
    import httpx

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    if args.local:
        return _sign_local(file_path, args)

    return _sign_remote(file_path, args)


def _sign_local(file_path: Path, args: argparse.Namespace) -> int:
    """Sign a file locally using a local certificate."""
    try:
        # Add parent directory to path for imports
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.core.signing_engine import SigningEngine, create_self_signed_cert

        content = file_path.read_bytes()

        # Check for local certificates
        cert_dir = Path(args.cert_dir or "./certs")
        cert_path = cert_dir / "default.pem"
        key_path = cert_dir / "default.key"

        if not cert_path.exists():
            print("No local certificate found. Generating self-signed cert...")
            cert_pem, key_pem = create_self_signed_cert()
            cert_dir.mkdir(parents=True, exist_ok=True)
            cert_path.write_bytes(cert_pem)
            key_path.write_bytes(key_pem)
            print(f"Certificate saved to {cert_dir}/")
        else:
            cert_pem = cert_path.read_bytes()
            key_pem = key_path.read_bytes()

        engine = SigningEngine(private_key_pem=key_pem, certificate_pem=cert_pem)
        result = engine.sign(content, algorithm=args.algorithm)

        output = {
            "status": "completed",
            "file": str(file_path),
            **result.to_dict(),
        }

        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(output, indent=2))
            print(f"Signature saved to {output_path}")
        else:
            print_json(output)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _sign_remote(file_path: Path, args: argparse.Namespace) -> int:
    """Sign a file via the remote service API."""
    import httpx

    base_url = get_base_url()
    headers = get_headers()

    print(f"Submitting {file_path.name} to {base_url}...")

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            data = {"algorithm": args.algorithm}
            if args.profile:
                data["profile"] = args.profile

            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{base_url}/api/v1/sign",
                    files=files,
                    data=data,
                    headers=headers,
                )

        if response.status_code != 202:
            print(f"Error: HTTP {response.status_code}", file=sys.stderr)
            print(response.text, file=sys.stderr)
            return 1

        result = response.json()
        job_id = result["job_id"]
        print(f"Job submitted: {job_id}")

        if not args.wait:
            print_json(result)
            return 0

        # Poll for completion
        print("Waiting for signing to complete...")
        return _poll_status(job_id, timeout=args.timeout)

    except httpx.ConnectError:
        print(
            f"Error: Cannot connect to {base_url}. Is the service running?",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _poll_status(job_id: str, timeout: int = 120) -> int:
    """Poll for job completion."""
    import httpx

    base_url = get_base_url()
    headers = get_headers()
    elapsed = 0
    interval = 3

    with httpx.Client(timeout=30.0) as client:
        while elapsed < timeout:
            response = client.get(
                f"{base_url}/api/v1/status/{job_id}",
                headers=headers,
            )

            if response.status_code != 200:
                print(f"Error checking status: HTTP {response.status_code}", file=sys.stderr)
                return 1

            result = response.json()
            status = result["status"]

            if status == "completed":
                print("Signing completed!")
                print_json(result)
                return 0
            elif status == "failed":
                print(f"Signing failed: {result.get('error_message', 'Unknown error')}", file=sys.stderr)
                return 1

            print(f"  Status: {status} ({elapsed}s/{timeout}s)")
            time.sleep(interval)
            elapsed += interval

    print(f"Timeout after {timeout}s", file=sys.stderr)
    return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify a signed macro file."""
    import httpx

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    if args.local:
        return _verify_local(file_path, args)

    base_url = get_base_url()
    headers = get_headers()

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            data = {
                "signature": args.signature,
                "algorithm": args.algorithm,
            }

            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{base_url}/api/v1/verify",
                    files=files,
                    data=data,
                    headers=headers,
                )

        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}", file=sys.stderr)
            return 1

        result = response.json()
        print_json(result)
        return 0 if result.get("is_valid") else 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _verify_local(file_path: Path, args: argparse.Namespace) -> int:
    """Verify a file locally."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.core.signing_engine import SigningEngine

        content = file_path.read_bytes()
        signature = bytes.fromhex(args.signature)

        cert_dir = Path(args.cert_dir or "./certs")
        cert_path = cert_dir / "default.pem"

        if not cert_path.exists():
            print("Error: No certificate found for verification", file=sys.stderr)
            return 1

        cert_pem = cert_path.read_bytes()
        engine = SigningEngine(certificate_pem=cert_pem)
        result = engine.verify(content, signature, algorithm=args.algorithm)

        print_json(result.to_dict())
        return 0 if result.is_valid else 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Check signing job status."""
    import httpx

    base_url = get_base_url()
    headers = get_headers()

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{base_url}/api/v1/status/{args.job_id}",
                headers=headers,
            )

        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}", file=sys.stderr)
            return 1

        print_json(response.json())
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_health(args: argparse.Namespace) -> int:
    """Check service health."""
    import httpx

    base_url = get_base_url()

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}/api/v1/health")

        result = response.json()
        print_json(result)
        return 0 if result.get("status") == "healthy" else 1

    except httpx.ConnectError:
        print(f"Error: Cannot connect to {base_url}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_cert(args: argparse.Namespace) -> int:
    """Generate a self-signed certificate for development."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.core.signing_engine import create_self_signed_cert

        cert_pem, key_pem = create_self_signed_cert(
            common_name=args.name,
            organization=args.organization,
            days_valid=args.days,
            key_size=args.key_size,
        )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cert_path = output_dir / f"{args.cert_name}.pem"
        key_path = output_dir / f"{args.cert_name}.key"

        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)

        print(f"Certificate generated:")
        print(f"  Certificate: {cert_path}")
        print(f"  Private key: {key_path}")
        print(f"  Common Name: {args.name}")
        print(f"  Valid for: {args.days} days")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_sign_vba(args: argparse.Namespace) -> int:
    """Sign an Office macro file with embedded VBA project signature."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.core.vba_signing import (
            VBASigningEngine,
            create_code_signing_pfx,
        )

        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            return 1

        content = file_path.read_bytes()

        # Load or generate certificate
        cert_dir = Path(args.cert_dir or "./certs")
        cert_path = cert_dir / "default.pem"
        key_path = cert_dir / "default.key"
        pfx_path = cert_dir / "default.pfx"

        if pfx_path.exists() and cert_path.exists() and key_path.exists():
            print(f"Using existing certificate from {cert_dir}/")
            cert_pem = cert_path.read_bytes()
            key_pem = key_path.read_bytes()
        elif cert_path.exists() and key_path.exists():
            print(f"Using existing PEM certificate, generating PFX...")
            cert_pem = cert_path.read_bytes()
            key_pem = key_path.read_bytes()
            from src.core.vba_signing import pem_to_pfx
            pfx_bytes = pem_to_pfx(cert_pem, key_pem)
            pfx_path.write_bytes(pfx_bytes)
            print(f"PFX saved to {pfx_path}")
        else:
            print("No certificate found. Generating code-signing certificate...")
            cert_dir.mkdir(parents=True, exist_ok=True)
            pfx_bytes, cert_pem, key_pem = create_code_signing_pfx(
                common_name=args.name or "Macro Sign Service Dev",
                organization=args.organization or "Development",
                days_valid=args.days or 365,
            )
            cert_path.write_bytes(cert_pem)
            key_path.write_bytes(key_pem)
            pfx_path.write_bytes(pfx_bytes)
            print(f"Certificate generated in {cert_dir}/")

        engine = VBASigningEngine(
            certificate_pem=cert_pem,
            private_key_pem=key_pem,
        )
        result = engine.sign_file(content, file_path.name, algorithm=args.algorithm)

        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = file_path.parent / f"{file_path.stem}_signed{file_path.suffix}"

        output_path.write_bytes(result.signed_file_bytes)

        print(f"\nSigning complete!")
        print(f"  Method: {result.signing_method}")
        print(f"  Input:  {file_path}")
        print(f"  Output: {output_path}")
        print(f"  Certificate: {result.certificate_subject}")
        print(f"  Fingerprint: {result.certificate_fingerprint}")
        print(f"  Algorithm: {result.algorithm}")

        if result.signing_method == "package-for-windows":
            print(f"\n  NOTE: No Windows signing tool was found on this system.")
            print(f"  The output file is unsigned. To sign on Windows:")
            print(f"  1. Copy {pfx_path} to the Windows machine")
            print(f"  2. Run the following PowerShell command:")
            print(f'     $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2("{pfx_path.name}", "", "Exportable")')
            print(f'     Set-AuthenticodeSignature -FilePath "{output_path.name}" -Certificate $cert')
            print(f"  Or use: scripts/sign-vba.ps1 -File \"{output_path.name}\" -PfxFile \"{pfx_path.name}\"")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_pfx(args: argparse.Namespace) -> int:
    """Generate a PFX code-signing certificate for Windows VBA signing."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.core.vba_signing import create_code_signing_pfx

        pfx_bytes, cert_pem, key_pem = create_code_signing_pfx(
            common_name=args.name,
            organization=args.organization,
            days_valid=args.days,
            key_size=args.key_size,
        )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pfx_path = output_dir / f"{args.cert_name}.pfx"
        cert_path = output_dir / f"{args.cert_name}.pem"
        key_path = output_dir / f"{args.cert_name}.key"

        pfx_path.write_bytes(pfx_bytes)
        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)

        print(f"Code-signing certificate generated:")
        print(f"  PFX (Windows): {pfx_path}")
        print(f"  Certificate:   {cert_path}")
        print(f"  Private key:   {key_path}")
        print(f"  Common Name:   {args.name}")
        print(f"  Valid for:     {args.days} days")
        print(f"\nTo sign on Windows:")
        print(f'  $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2("{pfx_path}", "", "Exportable")')
        print(f'  Set-AuthenticodeSignature -FilePath "macro.xlsm" -Certificate $cert')
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_cert_info(args: argparse.Namespace) -> int:
    """Display certificate details and signing proof."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.core.vba_signing import get_certificate_details

        cert_dir = Path(args.cert_dir or "./certs")
        cert_name = args.cert_name or "default"
        cert_path = cert_dir / f"{cert_name}.pem"

        if not cert_path.exists():
            print(f"Error: Certificate not found: {cert_path}", file=sys.stderr)
            return 1

        cert_pem = cert_path.read_bytes()
        details = get_certificate_details(cert_pem)

        # Check if PFX exists
        pfx_path = cert_dir / f"{cert_name}.pfx"
        details["pfx_available"] = pfx_path.exists()

        # Remove the full PEM from display (too long)
        display = {k: v for k, v in details.items() if k != "certificate_pem"}

        print(f"Certificate: {cert_path}")
        print_json(display)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="macro-sign",
        description="Macro Sign Service CLI - Sign and verify VBA macros",
    )
    parser.add_argument(
        "--url",
        help="Service URL (default: MACRO_SIGN_URL env var or http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        help="API key (default: MACRO_SIGN_API_KEY env var)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Sign command
    sign_parser = subparsers.add_parser("sign", help="Sign a macro file")
    sign_parser.add_argument("file", help="Path to macro file")
    sign_parser.add_argument("--profile", "-p", help="Signing profile name")
    sign_parser.add_argument(
        "--algorithm", "-a", default="sha256", choices=["sha256", "sha384", "sha512"]
    )
    sign_parser.add_argument("--local", "-l", action="store_true", help="Sign locally")
    sign_parser.add_argument("--cert-dir", help="Local certificate directory")
    sign_parser.add_argument("--output", "-o", help="Output file for signature")
    sign_parser.add_argument("--wait", "-w", action="store_true", default=True, help="Wait for completion")
    sign_parser.add_argument("--no-wait", action="store_false", dest="wait")
    sign_parser.add_argument("--timeout", "-t", type=int, default=120, help="Timeout in seconds")

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify a signed macro")
    verify_parser.add_argument("file", help="Path to macro file")
    verify_parser.add_argument("--signature", "-s", required=True, help="Hex-encoded signature")
    verify_parser.add_argument(
        "--algorithm", "-a", default="sha256", choices=["sha256", "sha384", "sha512"]
    )
    verify_parser.add_argument("--local", "-l", action="store_true", help="Verify locally")
    verify_parser.add_argument("--cert-dir", help="Local certificate directory")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check job status")
    status_parser.add_argument("job_id", help="Job ID")

    # Health command
    subparsers.add_parser("health", help="Check service health")

    # Sign VBA command (Office files with embedded signature)
    sign_vba_parser = subparsers.add_parser(
        "sign-vba", help="Sign Office macro file with embedded VBA signature"
    )
    sign_vba_parser.add_argument("file", help="Path to Office macro file (.xlsm, .docm, etc.)")
    sign_vba_parser.add_argument("--output", "-o", help="Output path for signed file")
    sign_vba_parser.add_argument(
        "--algorithm", "-a", default="sha256", choices=["sha256", "sha384", "sha512"]
    )
    sign_vba_parser.add_argument("--cert-dir", help="Certificate directory")
    sign_vba_parser.add_argument("--name", help="Certificate common name (for generation)")
    sign_vba_parser.add_argument("--organization", help="Certificate organization (for generation)")
    sign_vba_parser.add_argument("--days", type=int, help="Certificate validity days (for generation)")

    # Generate cert command
    cert_parser = subparsers.add_parser("generate-cert", help="Generate self-signed certificate")
    cert_parser.add_argument("--name", default="Macro Sign Service Dev", help="Common name")
    cert_parser.add_argument("--organization", default="Development", help="Organization")
    cert_parser.add_argument("--days", type=int, default=365, help="Days valid")
    cert_parser.add_argument("--key-size", type=int, default=2048, help="RSA key size")
    cert_parser.add_argument("--output-dir", default="./certs", help="Output directory")
    cert_parser.add_argument("--cert-name", default="default", help="Certificate file name")

    # Generate PFX command (Windows-compatible code signing cert)
    pfx_parser = subparsers.add_parser(
        "generate-pfx", help="Generate PFX code-signing certificate for Windows"
    )
    pfx_parser.add_argument("--name", default="Macro Sign Service Dev", help="Common name")
    pfx_parser.add_argument("--organization", default="Development", help="Organization")
    pfx_parser.add_argument("--days", type=int, default=365, help="Days valid")
    pfx_parser.add_argument("--key-size", type=int, default=2048, help="RSA key size")
    pfx_parser.add_argument("--output-dir", default="./certs", help="Output directory")
    pfx_parser.add_argument("--cert-name", default="default", help="Certificate file name")

    # Certificate info command
    info_parser = subparsers.add_parser(
        "cert-info", help="Display certificate details and signing proof"
    )
    info_parser.add_argument("--cert-dir", default="./certs", help="Certificate directory")
    info_parser.add_argument("--cert-name", default="default", help="Certificate name")

    args = parser.parse_args()

    # Override URL and API key if provided
    if args.url:
        os.environ["MACRO_SIGN_URL"] = args.url
    if args.api_key:
        os.environ["MACRO_SIGN_API_KEY"] = args.api_key

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "sign": cmd_sign,
        "sign-vba": cmd_sign_vba,
        "verify": cmd_verify,
        "status": cmd_status,
        "health": cmd_health,
        "generate-cert": cmd_generate_cert,
        "generate-pfx": cmd_generate_pfx,
        "cert-info": cmd_cert_info,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
