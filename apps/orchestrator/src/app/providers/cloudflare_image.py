from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import socket
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.providers.base import PermanentProviderError, RetryableProviderError
from app.services.artifacts import ArtifactStore
from app.services.image_validation import validate_image_bytes


DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"
MAX_PROMPT_CHARS = 2048
VISUAL_BIBLE = (
    "Cinematic illustrated Thai folktale, cohesive palette, consistent character design, "
    "no text, no watermark, subject centered for 16:9 crop."
)


class CloudflareImageClient(Protocol):
    def run(self, *, model: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class CloudflareImageProvider:
    provider = "cloudflare"
    output_extension = "jpg"

    def __init__(
        self,
        store: ArtifactStore,
        client: CloudflareImageClient,
        model: str = DEFAULT_MODEL,
        steps: int = 4,
    ) -> None:
        _parse_model(model)
        if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 8:
            raise ValueError("steps must be between 1 and 8")
        self.store = store
        self.client = client
        self.model = model
        self.steps = steps

    def generate(self, scene: dict[str, Any], output_path: str) -> dict[str, Any]:
        try:
            self.store.path(output_path)
        except (TypeError, ValueError, OSError) as error:
            raise PermanentProviderError("image output path is invalid") from error
        if not isinstance(output_path, str) or not output_path.lower().endswith(".jpg"):
            raise PermanentProviderError("image output path must use .jpg")

        scene_id = scene.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id.strip():
            raise PermanentProviderError("image scene is invalid")
        prompt = self._compose_prompt(scene)
        seed_material = "\0".join((self.model, scene_id, prompt)).encode(
            "utf-8", errors="surrogatepass"
        )
        digest_value = int.from_bytes(hashlib.sha256(seed_material).digest(), "big")
        seed = (digest_value % ((1 << 31) - 1)) + 1
        payload = {"prompt": prompt, "steps": self.steps, "seed": seed}

        try:
            envelope = self.client.run(model=self.model, payload=payload)
        except RetryableProviderError as error:
            raise RetryableProviderError("Cloudflare image request failed temporarily") from error
        except PermanentProviderError as error:
            raise PermanentProviderError("Cloudflare image request failed") from error
        except Exception as error:
            raise PermanentProviderError("Cloudflare image request failed") from error

        try:
            if (
                not isinstance(envelope, dict)
                or envelope.get("success") is not True
                or not isinstance(envelope.get("result"), dict)
                or not isinstance(envelope.get("errors"), list)
            ):
                raise ValueError
            encoded = envelope["result"]["image"]
            if not isinstance(encoded, str) or not encoded:
                raise ValueError
            content = base64.b64decode(encoded, validate=True)
            validate_image_bytes(content, "image/jpeg")
        except (KeyError, TypeError, ValueError, binascii.Error) as error:
            raise PermanentProviderError("Cloudflare image response is invalid") from error

        try:
            relative_path = self.store.publish_bytes_set({output_path: content})[output_path]
        except OSError as error:
            raise PermanentProviderError("Cloudflare image output could not be published") from error
        return {
            "provider": self.provider,
            "model": self.model,
            "seed": seed,
            "steps": self.steps,
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8", errors="surrogatepass")).hexdigest(),
            "output_path": relative_path,
            "mime_type": "image/jpeg",
        }

    @staticmethod
    def _compose_prompt(scene: dict[str, Any]) -> str:
        visual_bible = _normalize_whitespace(VISUAL_BIBLE)
        title = _normalize_whitespace(str(scene.get("title", "")))
        scene_prompt = _normalize_whitespace(str(scene.get("prompt", "")))
        narration = _normalize_whitespace(str(scene.get("narration", "")))
        fixed = f"{visual_bible} Title: {title}. Scene: {scene_prompt}. Narration: "
        if len(fixed) > MAX_PROMPT_CHARS:
            raise PermanentProviderError("image prompt fixed content exceeds the size limit")
        return fixed + narration[: MAX_PROMPT_CHARS - len(fixed)]


class CloudflareRESTImageClient:
    def __init__(
        self,
        account_id: str,
        api_token: str,
        timeout_seconds: float = 60,
        max_response_bytes: int = 16_000_000,
    ) -> None:
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("account_id must be nonempty")
        if not isinstance(api_token, str) or not api_token.strip():
            raise ValueError("api_token must be nonempty")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(max_response_bytes, int) or isinstance(max_response_bytes, bool) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self._account_id = account_id
        self._api_token = api_token
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    def run(self, *, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            owner, model_name = _parse_model(model)
        except ValueError as error:
            raise PermanentProviderError("Cloudflare image model is invalid") from error
        if not isinstance(payload, dict):
            raise PermanentProviderError("Cloudflare image request is invalid")
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{quote(self._account_id, safe='')}/ai/run/@cf/"
            f"{quote(owner, safe='')}/{quote(model_name, safe='')}"
        )
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise PermanentProviderError("Cloudflare image request is invalid") from error
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read(self._max_response_bytes + 1)
        except HTTPError as error:
            if error.code == 429 or 500 <= error.code <= 599:
                raise RetryableProviderError("Cloudflare image service is temporarily unavailable") from error
            raise PermanentProviderError("Cloudflare image request was rejected") from error
        except (socket.timeout, TimeoutError, URLError) as error:
            raise RetryableProviderError("Cloudflare image service is temporarily unavailable") from error
        except OSError as error:
            raise PermanentProviderError("Cloudflare image request failed") from error

        if len(response_body) > self._max_response_bytes:
            raise PermanentProviderError("Cloudflare image response exceeds the size limit")
        try:
            envelope = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PermanentProviderError("Cloudflare image response is invalid") from error
        if (
            not isinstance(envelope, dict)
            or envelope.get("success") is not True
            or not isinstance(envelope.get("result"), dict)
            or not isinstance(envelope.get("errors", []), list)
        ):
            raise PermanentProviderError("Cloudflare image response is invalid")
        return envelope


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_model(model: str) -> tuple[str, str]:
    if not isinstance(model, str):
        raise ValueError("model must use canonical Cloudflare syntax")
    match = re.fullmatch(
        r"@cf/([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9][A-Za-z0-9._-]*)",
        model,
    )
    if match is None:
        raise ValueError("model must use canonical Cloudflare syntax")
    return match.group(1), match.group(2)
