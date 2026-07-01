from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any, Protocol, get_type_hints

try:
    from pydantic import BaseModel, ValidationError
except Exception:
    class ValidationError(ValueError):
        pass

    class BaseModel:
        def __init__(self, **data: Any) -> None:
            annotations = get_type_hints(type(self))
            for field in annotations:
                if field not in data:
                    raise ValidationError(f"Missing field: {field}")
                setattr(self, field, data[field])

        @classmethod
        def model_validate(cls, data: Any):
            if not isinstance(data, dict):
                raise ValidationError("Model input must be a dict")
            values: dict[str, Any] = {}
            for field, annotation in get_type_hints(cls).items():
                if field not in data:
                    raise ValidationError(f"Missing field: {field}")
                value = data[field]
                origin = getattr(annotation, "__origin__", None)
                if origin is list:
                    inner = annotation.__args__[0]
                    if not isinstance(value, list):
                        raise ValidationError(f"Field {field} must be a list")
                    value = [
                        inner.model_validate(item) if isinstance(inner, type) and issubclass(inner, BaseModel) else item
                        for item in value
                    ]
                values[field] = value
            return cls(**values)

        def model_dump(self) -> dict[str, Any]:
            payload: dict[str, Any] = {}
            for field in get_type_hints(type(self)):
                value = getattr(self, field)
                if isinstance(value, list):
                    payload[field] = [
                        item.model_dump() if isinstance(item, BaseModel) else item for item in value
                    ]
                else:
                    payload[field] = value.model_dump() if isinstance(value, BaseModel) else value
            return payload

from app.providers.base import PermanentProviderError, RetryableProviderError

_THAI_PATTERN = re.compile(r"[\u0E00-\u0E7F]")


class GeminiSceneResponse(BaseModel):
    title: str
    narration: str
    image_prompt: str


class GeminiStoryResponse(BaseModel):
    story_title: str
    scenes: list[GeminiSceneResponse]


class GeminiStoryClient(Protocol):
    def generate_story(
        self,
        *,
        model: str,
        prompt: str,
        response_schema: type[BaseModel],
        temperature: float,
    ) -> dict[str, Any]:
        ...


class GoogleGenAIStoryClient:
    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    def generate_story(
        self,
        *,
        model: str,
        prompt: str,
        response_schema: type[BaseModel],
        temperature: float,
    ) -> dict[str, Any]:
        try:
            response = self._generate(model, prompt, response_schema, temperature)
            parsed = getattr(response, "parsed", None)
            if parsed is None:
                raise RetryableProviderError("Gemini returned no structured story")
            return parsed.model_dump()
        except (RetryableProviderError, PermanentProviderError):
            raise
        except Exception as error:
            status = getattr(error, "status_code", None) or getattr(error, "code", None)
            if status in {408, 429, 500, 502, 503, 504}:
                raise RetryableProviderError("Gemini story request temporarily failed") from error
            raise PermanentProviderError("Gemini story request was rejected") from error

    def _generate(
        self,
        model: str,
        prompt: str,
        response_schema: type[BaseModel],
        temperature: float,
    ) -> Any:
        from google.genai import types

        return self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=temperature,
            ),
        )


class GeminiStoryProvider:
    provider = "google"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        max_attempts: int = 3,
        temperature: float = 0.7,
        client: GeminiStoryClient | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> None:
        if not api_key.strip():
            raise PermanentProviderError("Gemini API key is required")
        if not model.strip():
            raise ValueError("model must not be empty")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if not math.isfinite(temperature) or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        self.api_key = api_key
        self.model = model.strip()
        self.max_attempts = max_attempts
        self.temperature = temperature
        self.client = client or GoogleGenAIStoryClient(api_key)
        self.sleep = sleep

    def generate_story(
        self,
        topic: str,
        duration_seconds: int,
        language: str,
        profile: str,
        script_version: int,
    ) -> dict[str, Any]:
        normalized_topic = re.sub(r"\s+", " ", topic).strip()
        if not normalized_topic:
            raise PermanentProviderError("Story topic is required")
        if len(normalized_topic) > 500:
            raise PermanentProviderError("Story topic is too long")
        scene_count = max(3, min(8, round(duration_seconds / 10)))
        prompt = self._build_prompt(
            normalized_topic, duration_seconds, language, profile, script_version, scene_count
        )

        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self.client.generate_story(
                    model=self.model,
                    prompt=prompt,
                    response_schema=GeminiStoryResponse,
                    temperature=self.temperature,
                )
                response = GeminiStoryResponse.model_validate(payload)
                return self._normalize_story(response, scene_count)
            except RetryableProviderError as error:
                if attempt == self.max_attempts:
                    raise RetryableProviderError(
                        f"Gemini story generation failed after {self.max_attempts} attempts"
                    ) from error
                self.sleep(min(2 ** (attempt - 1), 4))
            except ValidationError as error:
                raise PermanentProviderError("Gemini story response was invalid") from error
            except PermanentProviderError as error:
                raise self._sanitize_permanent(error) from error
            except Exception as error:
                raise PermanentProviderError("Gemini story request failed permanently") from error
        raise AssertionError("unreachable")

    def _build_prompt(
        self,
        topic: str,
        duration_seconds: int,
        language: str,
        profile: str,
        script_version: int,
        scene_count: int,
    ) -> str:
        return (
            "Generate exactly "
            f"{scene_count} scenes for a short YouTube story.\n"
            f"Topic: {topic}\n"
            f"Duration seconds: {duration_seconds}\n"
            f"Language: {language}\n"
            f"Profile: {profile}\n"
            f"Script version: {script_version}\n"
            "Requirements:\n"
            "- Thai narration for every scene.\n"
            "- English image prompts for every scene.\n"
            "- No dialogue formatting and no written text in images.\n"
            "- Keep the main subject near the center for 16:9 crops.\n"
            "- Return only structured JSON matching the requested schema.\n"
        )

    def _normalize_story(
        self, response: GeminiStoryResponse, expected_scene_count: int
    ) -> dict[str, Any]:
        title = self._clean_text(response.story_title, "story title", 200)
        if len(response.scenes) != expected_scene_count:
            raise PermanentProviderError("Gemini story response used the wrong scene count")

        seen_titles: set[str] = set()
        scenes: list[dict[str, Any]] = []
        for index, scene in enumerate(response.scenes, 1):
            scene_title = self._clean_text(scene.title, "scene title", 200)
            lowered = scene_title.casefold()
            if lowered in seen_titles:
                raise PermanentProviderError("Gemini story response repeated a scene title")
            seen_titles.add(lowered)

            narration = self._clean_text(scene.narration, "scene narration", 4000)
            if not _THAI_PATTERN.search(narration):
                raise PermanentProviderError("Gemini story narration must contain Thai text")

            prompt = self._clean_text(scene.image_prompt, "scene image prompt", 2048)
            scenes.append(
                {
                    "scene_id": f"scene_{index:03d}",
                    "title": scene_title,
                    "narration": narration,
                    "prompt": prompt,
                    "motion": "slow_push",
                    "focal_point": [0.5, 0.5],
                }
            )

        return {
            "outline": {"title": title, "beats": [scene["title"] for scene in scenes]},
            "script": "\n\n".join(scene["narration"] for scene in scenes),
            "scenes": scenes,
        }

    @staticmethod
    def _clean_text(value: str, field_name: str, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", value).strip()
        if not normalized:
            raise PermanentProviderError(f"Gemini story {field_name} is required")
        if len(normalized) > limit:
            raise PermanentProviderError(f"Gemini story {field_name} is too long")
        return normalized

    @staticmethod
    def _sanitize_permanent(error: PermanentProviderError) -> PermanentProviderError:
        message = str(error)
        if "after " in message:
            return error
        return PermanentProviderError("Gemini story request failed permanently")
