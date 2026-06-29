from __future__ import annotations

from typing import Any, TypedDict


class VideoProjectState(TypedDict, total=False):
    project_id: str
    status: str
    created_at: str
    updated_at: str
    topic: str
    target_duration_seconds: int
    target_language: str
    channel_style_profile: str
    outline: dict[str, Any]
    outline_path: str | None
    outline_review: dict[str, Any]
    script: str
    script_path: str | None
    script_version: int
    script_review: dict[str, Any]
    script_approved: bool
    scenes: list[dict[str, Any]]
    scenes_path: str | None
    scene_count: int
    image_budget: dict[str, Any]
    image_jobs: list[dict[str, Any]]
    generated_images: list[dict[str, Any]]
    failed_scene_ids: list[str]
    voice_provider: str
    voice_path: str | None
    audio_duration_seconds: float | None
    audio_analysis: dict[str, Any]
    timeline: list[dict[str, Any]]
    render_payload_path: str | None
    video_path: str | None
    quality_report: dict[str, Any]
    final_approved: bool
    current_node: str | None
    waiting_for: str | None
    retry_counts: dict[str, int]
