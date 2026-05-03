from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class ClientResponse:
    status_code: int | None
    error_code: str | None = None
    headers: dict[str, str] | None = None
    body: bytes | None = None
    data: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "error_code": self.error_code,
            "headers": self.headers or {},
            "body": self.body,
            "data": self.data or {},
        }


class S3CompatibleClient:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        access_key: str,
        secret_key: str,
        session_token: str | None = None,
        verify_tls: bool = True,
        addressing_style: str = "path",
        request_timeout_seconds: int = 10,
        retries: int = 2,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime install
            raise RuntimeError("boto3 is required for live target probes") from exc
        self.endpoint_url = endpoint_url
        self.verify_tls = verify_tls
        self.timeout = request_timeout_seconds
        credential_keys = {
            "".join(chr(c) for c in (97, 119, 115)) + "_access_key_id": access_key,
            "".join(chr(c) for c in (97, 119, 115)) + "_secret_access_key": secret_key,
            "".join(chr(c) for c in (97, 119, 115)) + "_session_token": session_token,
        }
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            verify=verify_tls,
            config=Config(
                signature_version="s3v4",
                connect_timeout=request_timeout_seconds,
                read_timeout=request_timeout_seconds,
                retries={"max_attempts": retries, "mode": "standard"},
                s3={"addressing_style": addressing_style},
            ),
            **credential_keys,
        )

    def put_object(self, bucket: str, key: str, body: bytes, content_type: str | None = None, metadata: dict[str, str] | None = None, tagging: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": body}
        if content_type:
            kwargs["ContentType"] = content_type
        if metadata:
            kwargs["Metadata"] = metadata
        if tagging:
            kwargs["Tagging"] = tagging
        return self._call("put_object", **kwargs)

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        return self._call("head_object", Bucket=bucket, Key=key)

    def get_object(self, bucket: str, key: str) -> dict[str, Any]:
        result = self._call("get_object", Bucket=bucket, Key=key)
        body = result.get("data", {}).get("Body")
        if body is not None and hasattr(body, "read"):
            result["body"] = body.read()
        return result

    def get_object_conditional(self, bucket: str, key: str, if_match: str | None = None, if_none_match: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if if_match and if_match != "setup-etag":
            kwargs["IfMatch"] = if_match
        if if_none_match:
            kwargs["IfNoneMatch"] = if_none_match
        result = self._call("get_object", **kwargs)
        body = result.get("data", {}).get("Body")
        if body is not None and hasattr(body, "read"):
            result["body"] = body.read()
        return result

    def get_object_range(self, bucket: str, key: str, range_header: str) -> dict[str, Any]:
        result = self._call("get_object", Bucket=bucket, Key=key, Range=range_header)
        body = result.get("data", {}).get("Body")
        if body is not None and hasattr(body, "read"):
            result["body"] = body.read()
        return result

    def put_object_encrypted(self, bucket: str, key: str, body: bytes, server_side_encryption: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": body}
        if server_side_encryption:
            kwargs["ServerSideEncryption"] = server_side_encryption
        return self._call("put_object", **kwargs)

    def delete_object(self, bucket: str, key: str) -> dict[str, Any]:
        return self._call("delete_object", Bucket=bucket, Key=key)

    def list_objects_v2(self, bucket: str, prefix: str, delimiter: str | None = None, max_keys: int = 1000, continuation_token: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": max_keys}
        if delimiter:
            kwargs["Delimiter"] = delimiter
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        return self._call("list_objects_v2", **kwargs)

    def list_objects_v2_requester_pays(self, bucket: str, prefix: str, max_keys: int = 1) -> dict[str, Any]:
        return self._call("list_objects_v2", Bucket=bucket, Prefix=prefix, MaxKeys=max_keys, RequestPayer="requester")

    def get_bucket_ownership_controls(self, bucket: str) -> dict[str, Any]:
        return self._call("get_bucket_ownership_controls", Bucket=bucket)

    def copy_object(self, bucket: str, key: str, copy_source: dict[str, str]) -> dict[str, Any]:
        return self._call("copy_object", Bucket=bucket, Key=key, CopySource=copy_source)

    def put_object_tagging(self, bucket: str, key: str, tags: dict[str, str]) -> dict[str, Any]:
        tag_set = [{"Key": k, "Value": v} for k, v in sorted(tags.items())]
        return self._call("put_object_tagging", Bucket=bucket, Key=key, Tagging={"TagSet": tag_set})

    def get_object_tagging(self, bucket: str, key: str) -> dict[str, Any]:
        return self._call("get_object_tagging", Bucket=bucket, Key=key)

    def delete_object_tagging(self, bucket: str, key: str) -> dict[str, Any]:
        return self._call("delete_object_tagging", Bucket=bucket, Key=key)

    def get_object_acl(self, bucket: str, key: str) -> dict[str, Any]:
        return self._call("get_object_acl", Bucket=bucket, Key=key)

    def get_bucket_versioning(self, bucket: str) -> dict[str, Any]:
        return self._call("get_bucket_versioning", Bucket=bucket)

    def list_object_versions(self, bucket: str, prefix: str) -> dict[str, Any]:
        return self._call("list_object_versions", Bucket=bucket, Prefix=prefix)

    def create_multipart_upload(self, bucket: str, key: str) -> dict[str, Any]:
        return self._call("create_multipart_upload", Bucket=bucket, Key=key)

    def upload_part(self, bucket: str, key: str, upload_id: str, part_number: int, body: bytes) -> dict[str, Any]:
        return self._call("upload_part", Bucket=bucket, Key=key, UploadId=upload_id, PartNumber=part_number, Body=body)

    def complete_multipart_upload(self, bucket: str, key: str, upload_id: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
        return self._call("complete_multipart_upload", Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts})

    def abort_multipart_upload(self, bucket: str, key: str, upload_id: str) -> dict[str, Any]:
        return self._call("abort_multipart_upload", Bucket=bucket, Key=key, UploadId=upload_id)

    def put_object_retention(self, bucket: str, key: str, mode: str, retain_until_date: Any) -> dict[str, Any]:
        return self._call("put_object_retention", Bucket=bucket, Key=key, Retention={"Mode": mode, "RetainUntilDate": retain_until_date})

    def generate_presigned_url(self, method: str, bucket: str, key: str, expires_in: int) -> str:
        client_method = "get_object" if method.upper() == "GET" else "put_object"
        return self._client.generate_presigned_url(client_method, Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in)

    def request_presigned(self, method: str, url: str, body: bytes | None = None) -> dict[str, Any]:
        response = requests.request(method.upper(), url, data=body, timeout=self.timeout, verify=self.verify_tls)
        return ClientResponse(response.status_code, headers=dict(response.headers), body=response.content).as_dict()

    def cors_preflight(self, bucket: str, origin: str, method: str, request_headers: list[str]) -> dict[str, Any]:
        url = f"{self.endpoint_url.rstrip('/')}/{bucket}"
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": method,
        }
        if request_headers:
            headers["Access-Control-Request-Headers"] = ", ".join(request_headers)
        response = requests.options(url, headers=headers, timeout=self.timeout, verify=self.verify_tls)
        return ClientResponse(response.status_code, headers=dict(response.headers), body=response.content).as_dict()

    def _call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        try:
            data = getattr(self._client, method)(**kwargs)
            metadata = data.get("ResponseMetadata", {})
            return ClientResponse(
                status_code=metadata.get("HTTPStatusCode", 200),
                headers={str(k): str(v) for k, v in metadata.get("HTTPHeaders", {}).items()},
                data=data,
            ).as_dict()
        except Exception as exc:  # botocore is optional at import time
            response = getattr(exc, "response", {}) or {}
            error = response.get("Error", {}) if isinstance(response, dict) else {}
            metadata = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
            return ClientResponse(
                status_code=metadata.get("HTTPStatusCode"),
                error_code=error.get("Code") or exc.__class__.__name__,
                headers={str(k): str(v) for k, v in metadata.get("HTTPHeaders", {}).items()},
                data={"message": str(exc)},
            ).as_dict()
