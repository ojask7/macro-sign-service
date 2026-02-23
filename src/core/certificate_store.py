"""
Certificate store abstraction layer.
Supports multiple backends: local filesystem, HashiCorp Vault, AWS KMS, Azure Key Vault.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any, Optional

from src.config.logging import get_logger
from src.config.settings import CertStoreBackend, get_settings

logger = get_logger(__name__)


class CertificateStoreError(Exception):
    """Raised when a certificate store operation fails."""

    pass


class CertificateInfo:
    """Information about a stored certificate."""

    def __init__(
        self,
        name: str,
        certificate_pem: bytes,
        private_key_pem: Optional[bytes] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.certificate_pem = certificate_pem
        self.private_key_pem = private_key_pem
        self.metadata = metadata or {}


class BaseCertificateStore(abc.ABC):
    """Abstract base class for certificate stores."""

    @abc.abstractmethod
    async def get_certificate(self, name: str) -> CertificateInfo:
        """Retrieve a certificate by name."""
        ...

    @abc.abstractmethod
    async def store_certificate(
        self,
        name: str,
        certificate_pem: bytes,
        private_key_pem: Optional[bytes] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Store a certificate."""
        ...

    @abc.abstractmethod
    async def list_certificates(self) -> list[str]:
        """List all certificate names."""
        ...

    @abc.abstractmethod
    async def delete_certificate(self, name: str) -> None:
        """Delete a certificate by name."""
        ...

    @abc.abstractmethod
    async def rotate_certificate(
        self,
        name: str,
        new_certificate_pem: bytes,
        new_private_key_pem: Optional[bytes] = None,
    ) -> None:
        """Rotate (replace) a certificate."""
        ...

    async def get_or_create_certificate(
        self,
        name: str,
        *,
        common_name: str,
        organization: str = "Macro Sign Service",
        days_valid: int = 365,
    ) -> CertificateInfo:
        """
        Retrieve a certificate by name, or auto-create a self-signed one if absent.

        This is the idempotent provisioning method used by the SNOW integration to
        ensure the test-domain certificate always exists without manual setup.
        """
        try:
            return await self.get_certificate(name)
        except CertificateStoreError:
            from src.core.signing_engine import create_self_signed_cert

            cert_pem, key_pem = create_self_signed_cert(
                common_name=common_name,
                organization=organization,
                days_valid=days_valid,
            )
            metadata: dict[str, Any] = {
                "common_name": common_name,
                "organization": organization,
                "auto_generated": True,
                "purpose": "test",
            }
            await self.store_certificate(name, cert_pem, key_pem, metadata)
            logger.info(
                "Auto-created certificate for key store",
                name=name,
                common_name=common_name,
            )
            return await self.get_certificate(name)


class LocalCertificateStore(BaseCertificateStore):
    """
    Local filesystem certificate store.
    Suitable for development and testing only.
    """

    def __init__(self, base_path: str = "./certs") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("Local certificate store initialized", path=str(self.base_path))

    async def get_certificate(self, name: str) -> CertificateInfo:
        cert_path = self.base_path / f"{name}.pem"
        key_path = self.base_path / f"{name}.key"

        if not cert_path.exists():
            raise CertificateStoreError(f"Certificate '{name}' not found")

        certificate_pem = cert_path.read_bytes()
        private_key_pem = key_path.read_bytes() if key_path.exists() else None

        meta_path = self.base_path / f"{name}.meta.json"
        metadata = {}
        if meta_path.exists():
            import json

            metadata = json.loads(meta_path.read_text())

        return CertificateInfo(
            name=name,
            certificate_pem=certificate_pem,
            private_key_pem=private_key_pem,
            metadata=metadata,
        )

    async def store_certificate(
        self,
        name: str,
        certificate_pem: bytes,
        private_key_pem: Optional[bytes] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        cert_path = self.base_path / f"{name}.pem"
        cert_path.write_bytes(certificate_pem)

        if private_key_pem:
            key_path = self.base_path / f"{name}.key"
            key_path.write_bytes(private_key_pem)

        if metadata:
            import json

            meta_path = self.base_path / f"{name}.meta.json"
            meta_path.write_text(json.dumps(metadata, indent=2))

        logger.info("Certificate stored", name=name)

    async def list_certificates(self) -> list[str]:
        return [
            p.stem for p in self.base_path.glob("*.pem") if not p.stem.endswith(".meta")
        ]

    async def delete_certificate(self, name: str) -> None:
        for suffix in [".pem", ".key", ".meta.json"]:
            path = self.base_path / f"{name}{suffix}"
            if path.exists():
                path.unlink()
        logger.info("Certificate deleted", name=name)

    async def rotate_certificate(
        self,
        name: str,
        new_certificate_pem: bytes,
        new_private_key_pem: Optional[bytes] = None,
    ) -> None:
        # Archive old certificate
        cert_path = self.base_path / f"{name}.pem"
        if cert_path.exists():
            import time

            archive_name = f"{name}.backup.{int(time.time())}"
            archive_path = self.base_path / f"{archive_name}.pem"
            archive_path.write_bytes(cert_path.read_bytes())

            key_path = self.base_path / f"{name}.key"
            if key_path.exists():
                archive_key = self.base_path / f"{archive_name}.key"
                archive_key.write_bytes(key_path.read_bytes())

        # Store new certificate
        await self.store_certificate(name, new_certificate_pem, new_private_key_pem)
        logger.info("Certificate rotated", name=name)


class VaultCertificateStore(BaseCertificateStore):
    """
    HashiCorp Vault certificate store.
    Uses the KV secrets engine to store certificates.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.vault_url = settings.vault.url
        self.vault_token = settings.vault.token
        self.mount_point = settings.vault.mount_point
        self.base_path = settings.vault.cert_path
        self._client = None
        logger.info("Vault certificate store initialized", url=self.vault_url)

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import hvac

                self._client = hvac.Client(
                    url=self.vault_url, token=self.vault_token
                )
                if not self._client.is_authenticated():
                    raise CertificateStoreError("Vault authentication failed")
            except ImportError:
                raise CertificateStoreError(
                    "hvac package not installed. Install with: pip install hvac"
                )
        return self._client

    async def get_certificate(self, name: str) -> CertificateInfo:
        client = self._get_client()
        path = f"{self.base_path}/{name}"
        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=self.mount_point
            )
            data = response["data"]["data"]
            return CertificateInfo(
                name=name,
                certificate_pem=data["certificate"].encode(),
                private_key_pem=(
                    data["private_key"].encode() if "private_key" in data else None
                ),
                metadata=data.get("metadata", {}),
            )
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to retrieve certificate '{name}' from Vault: {e}"
            ) from e

    async def store_certificate(
        self,
        name: str,
        certificate_pem: bytes,
        private_key_pem: Optional[bytes] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        client = self._get_client()
        path = f"{self.base_path}/{name}"
        data = {"certificate": certificate_pem.decode()}
        if private_key_pem:
            data["private_key"] = private_key_pem.decode()
        if metadata:
            data["metadata"] = metadata
        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=data, mount_point=self.mount_point
            )
            logger.info("Certificate stored in Vault", name=name)
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to store certificate in Vault: {e}"
            ) from e

    async def list_certificates(self) -> list[str]:
        client = self._get_client()
        try:
            response = client.secrets.kv.v2.list_secrets(
                path=self.base_path, mount_point=self.mount_point
            )
            return response["data"]["keys"]
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to list certificates from Vault: {e}"
            ) from e

    async def delete_certificate(self, name: str) -> None:
        client = self._get_client()
        path = f"{self.base_path}/{name}"
        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path, mount_point=self.mount_point
            )
            logger.info("Certificate deleted from Vault", name=name)
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to delete certificate from Vault: {e}"
            ) from e

    async def rotate_certificate(
        self,
        name: str,
        new_certificate_pem: bytes,
        new_private_key_pem: Optional[bytes] = None,
    ) -> None:
        # Vault handles versioning natively via KV v2
        await self.store_certificate(name, new_certificate_pem, new_private_key_pem)
        logger.info("Certificate rotated in Vault", name=name)


class AWSKMSCertificateStore(BaseCertificateStore):
    """
    AWS KMS / Secrets Manager certificate store.
    Uses AWS Secrets Manager for certificate storage and KMS for key management.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.region = settings.aws.region
        self._client = None
        logger.info("AWS KMS certificate store initialized", region=self.region)

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3

                settings = get_settings()
                kwargs: dict[str, Any] = {"region_name": self.region}
                if settings.aws.access_key_id:
                    kwargs["aws_access_key_id"] = settings.aws.access_key_id
                    kwargs["aws_secret_access_key"] = settings.aws.secret_access_key
                self._client = boto3.client("secretsmanager", **kwargs)
            except ImportError:
                raise CertificateStoreError(
                    "boto3 package not installed. Install with: pip install boto3"
                )
        return self._client

    async def get_certificate(self, name: str) -> CertificateInfo:
        import json

        client = self._get_client()
        try:
            response = client.get_secret_value(SecretId=f"macro-sign/{name}")
            data = json.loads(response["SecretString"])
            return CertificateInfo(
                name=name,
                certificate_pem=data["certificate"].encode(),
                private_key_pem=(
                    data["private_key"].encode() if "private_key" in data else None
                ),
                metadata=data.get("metadata", {}),
            )
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to retrieve certificate from AWS: {e}"
            ) from e

    async def store_certificate(
        self,
        name: str,
        certificate_pem: bytes,
        private_key_pem: Optional[bytes] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        import json

        client = self._get_client()
        data = {"certificate": certificate_pem.decode()}
        if private_key_pem:
            data["private_key"] = private_key_pem.decode()
        if metadata:
            data["metadata"] = metadata
        try:
            client.put_secret_value(
                SecretId=f"macro-sign/{name}",
                SecretString=json.dumps(data),
            )
            logger.info("Certificate stored in AWS Secrets Manager", name=name)
        except client.exceptions.ResourceNotFoundException:
            client.create_secret(
                Name=f"macro-sign/{name}",
                SecretString=json.dumps(data),
            )
            logger.info("Certificate created in AWS Secrets Manager", name=name)
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to store certificate in AWS: {e}"
            ) from e

    async def list_certificates(self) -> list[str]:
        client = self._get_client()
        try:
            response = client.list_secrets(
                Filters=[{"Key": "name", "Values": ["macro-sign/"]}]
            )
            return [
                s["Name"].replace("macro-sign/", "")
                for s in response.get("SecretList", [])
            ]
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to list certificates from AWS: {e}"
            ) from e

    async def delete_certificate(self, name: str) -> None:
        client = self._get_client()
        try:
            client.delete_secret(
                SecretId=f"macro-sign/{name}", ForceDeleteWithoutRecovery=True
            )
            logger.info("Certificate deleted from AWS", name=name)
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to delete certificate from AWS: {e}"
            ) from e

    async def rotate_certificate(
        self,
        name: str,
        new_certificate_pem: bytes,
        new_private_key_pem: Optional[bytes] = None,
    ) -> None:
        await self.store_certificate(name, new_certificate_pem, new_private_key_pem)
        logger.info("Certificate rotated in AWS", name=name)


class AzureKeyVaultCertificateStore(BaseCertificateStore):
    """
    Azure Key Vault certificate store.
    Uses Azure Key Vault Secrets to store PEM-encoded certificates and private keys.
    Supports DefaultAzureCredential (managed identity, env vars, CLI login).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.vault_url = settings.azure.keyvault_url
        if not self.vault_url:
            raise CertificateStoreError(
                "AZURE_KEYVAULT_URL environment variable is required for Azure Key Vault backend"
            )
        self._client = None
        logger.info("Azure Key Vault certificate store initialized", url=self.vault_url)

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from azure.identity import (
                    ClientSecretCredential,
                    DefaultAzureCredential,
                )
                from azure.keyvault.secrets import SecretClient

                settings = get_settings()
                # Use explicit service-principal creds if provided, else DefaultAzureCredential
                if settings.azure.tenant_id and settings.azure.client_id and settings.azure.client_secret:
                    credential = ClientSecretCredential(
                        tenant_id=settings.azure.tenant_id,
                        client_id=settings.azure.client_id,
                        client_secret=settings.azure.client_secret,
                    )
                else:
                    credential = DefaultAzureCredential()

                self._client = SecretClient(
                    vault_url=self.vault_url, credential=credential
                )
            except ImportError:
                raise CertificateStoreError(
                    "azure-keyvault-secrets and azure-identity packages are required. "
                    "Install with: pip install azure-keyvault-secrets azure-identity"
                )
        return self._client

    @staticmethod
    def _secret_name(name: str) -> str:
        """Convert certificate name to a valid Azure Key Vault secret name (no dots/slashes)."""
        return "macro-sign-" + name.replace(".", "-").replace("/", "-").replace("_", "-")

    async def get_certificate(self, name: str) -> CertificateInfo:
        import json

        client = self._get_client()
        secret_name = self._secret_name(name)
        try:
            secret = client.get_secret(secret_name)
            data = json.loads(secret.value)
            return CertificateInfo(
                name=name,
                certificate_pem=data["certificate"].encode(),
                private_key_pem=(
                    data["private_key"].encode() if data.get("private_key") else None
                ),
                metadata=data.get("metadata", {}),
            )
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to retrieve certificate '{name}' from Azure Key Vault: {e}"
            ) from e

    async def store_certificate(
        self,
        name: str,
        certificate_pem: bytes,
        private_key_pem: Optional[bytes] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        import json

        client = self._get_client()
        secret_name = self._secret_name(name)
        data: dict[str, Any] = {"certificate": certificate_pem.decode()}
        if private_key_pem:
            data["private_key"] = private_key_pem.decode()
        if metadata:
            data["metadata"] = metadata
        try:
            client.set_secret(secret_name, json.dumps(data))
            logger.info("Certificate stored in Azure Key Vault", name=name)
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to store certificate '{name}' in Azure Key Vault: {e}"
            ) from e

    async def list_certificates(self) -> list[str]:
        client = self._get_client()
        prefix = "macro-sign-"
        try:
            return [
                props.name[len(prefix):]
                for props in client.list_properties_of_secrets()
                if props.name.startswith(prefix) and props.enabled
            ]
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to list certificates from Azure Key Vault: {e}"
            ) from e

    async def delete_certificate(self, name: str) -> None:
        client = self._get_client()
        secret_name = self._secret_name(name)
        try:
            client.begin_delete_secret(secret_name).result()
            logger.info("Certificate deleted from Azure Key Vault", name=name)
        except Exception as e:
            raise CertificateStoreError(
                f"Failed to delete certificate '{name}' from Azure Key Vault: {e}"
            ) from e

    async def rotate_certificate(
        self,
        name: str,
        new_certificate_pem: bytes,
        new_private_key_pem: Optional[bytes] = None,
    ) -> None:
        # Azure Key Vault retains all previous versions automatically
        await self.store_certificate(name, new_certificate_pem, new_private_key_pem)
        logger.info("Certificate rotated in Azure Key Vault", name=name)


def get_certificate_store() -> BaseCertificateStore:
    """Factory function to get the appropriate certificate store backend."""
    settings = get_settings()
    backend = settings.certificate.store_backend

    if backend == CertStoreBackend.LOCAL:
        return LocalCertificateStore()
    elif backend == CertStoreBackend.HASHICORP_VAULT:
        return VaultCertificateStore()
    elif backend == CertStoreBackend.AWS_KMS:
        return AWSKMSCertificateStore()
    elif backend == CertStoreBackend.AZURE_KEYVAULT:
        return AzureKeyVaultCertificateStore()
    else:
        raise CertificateStoreError(f"Unknown certificate store backend: {backend}")
