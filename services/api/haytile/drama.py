"""Plan -> private character references -> native scene clips -> validated episode.

Generated dialogue and continuity still require human review. No lip-sync or
visual consistency guarantee is inferred from successful file decoding.
"""

import base64
import json
import math

from pydantic import BaseModel, Field, ValidationError

from . import providers, storage
from .db import Asset, Job, Project, Session, uid
from .media import inspect_media
from .video import assemble


class CharacterPlan(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    appearance: str = Field(min_length=1, max_length=700)
    wardrobe: str = Field(default="", max_length=500)
    voice: str = Field(default="", max_length=300)


class ScenePlan(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    dialogue: str = Field(default="", max_length=1500)
    characters: list[str] = Field(default_factory=list, max_length=2)


class Plan(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    continuity: str = Field(default="", max_length=1500)
    characters: list[CharacterPlan] = Field(min_length=1, max_length=2)
    scenes: list[ScenePlan] = Field(min_length=1, max_length=18)


def save_intermediate(job_id, user_id, title, data, mime):
    mime, text = inspect_media(data, mime, max_bytes=256 * 1024 * 1024)
    key = storage.put(data, mime)
    try:
        with Session.begin() as db:
            job = db.get(Job, job_id)
            if not job or job.status != "processing":
                raise providers.ProviderError("JOB_NO_LONGER_ACTIVE")
            asset = Asset(
                user_id=user_id,
                job_id=job_id,
                title=title[:120],
                mime=mime,
                key=key,
                size=len(data),
                text=text,
            )
            db.add(asset)
            db.flush()
            return asset.id
    except Exception:
        storage.delete(key)
        raise


def render_episode(job, params, model_config):
    duration = params.get("duration", 16)
    count = math.ceil(duration / 10)
    language = params.get("language", "ht")
    aspect = params.get("aspect", "16:9")
    prompt = f"""Create a production plan for a short drama in language {language} based on this idea:
{job.prompt}
Return ONLY valid JSON with this structure:
{{"title":"...","continuity":"shared setting, lighting, camera and story continuity","characters":[{{"name":"...","appearance":"stable appearance and personality","wardrobe":"exact clothes and accessories","voice":"voice description"}}],"scenes":[{{"title":"...","description":"action, camera and setting","dialogue":"exact spoken dialogue","characters":["character name"]}}]}}
Use one or two characters and exactly {count} scenes, for a final total of {duration} seconds.
Each scene lasts at most 10 seconds. Keep dialogue short enough to fit naturally.
Use only character names declared in characters. Preserve any dialogue the user supplied; never translate it without permission.
"""
    plan_params = {**params, "_max_output_tokens": 8192}
    raw, mime = providers.generate("text", model_config["text"], prompt, plan_params)
    text = raw.decode().strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    try:
        plan = Plan.model_validate_json(text)
    except (ValueError, ValidationError) as exc:
        raise providers.ProviderError("DRAMA_PLAN_INVALID") from exc
    names = {c.name for c in plan.characters}
    if (
        len(names) != len(plan.characters)
        or len(plan.scenes) != count
        or any(set(s.characters) - names for s in plan.scenes)
    ):
        raise providers.ProviderError("DRAMA_PLAN_INVALID")
    characters = [
        {
            "id": uid(),
            "name": c.name,
            "appearance": c.appearance,
            "wardrobe": c.wardrobe,
            "voice": c.voice,
            "language": language,
            "reference_asset_id": None,
        }
        for c in plan.characters
    ]
    by_name = {c["name"]: c for c in characters}
    base, remainder = divmod(duration, count)
    scenes = [
        {
            "id": uid(),
            "title": s.title,
            "description": s.description,
            "dialogue": s.dialogue,
            "duration": base + (index < remainder),
            "character_ids": [by_name[n]["id"] for n in s.characters],
            "asset_id": None,
        }
        for index, s in enumerate(plan.scenes)
    ]
    document = {
        "premise": job.prompt,
        "continuity": plan.continuity,
        "aspect": aspect,
        "characters": characters,
        "scenes": scenes,
    }
    with Session.begin() as db:
        project = Project(user_id=job.user_id, title=plan.title, document=document)
        db.add(project)
        db.flush()
        project_id = project.id
        row = db.get(Job, job.id)
        row.params = {**row.params, "project_id": project_id}
        row.progress = 20
    params["project_id"] = project_id

    def checkpoint(progress):
        with Session.begin() as db:
            row = db.get(Job, job.id)
            project = db.get(Project, project_id)
            if not row or row.status != "processing" or not project:
                raise providers.ProviderError("JOB_NO_LONGER_ACTIVE")
            # JSON columns need a new value, not an in-place mutation.
            project.document = json.loads(json.dumps(document))
            project.version += 1
            row.progress = progress

    references = {}
    for index, character in enumerate(characters):
        image_prompt = f"Character reference image, single person, neutral background, no captions. {character['name']}: {character['appearance']}. Clothes and accessories must be exactly: {character['wardrobe']}."
        image, mime = providers.generate(
            "image", model_config["image"], image_prompt, {"aspect": "1:1"}
        )
        if not mime.startswith("image/"):
            raise providers.ProviderError("DRAMA_REFERENCE_INVALID")
        asset_id = save_intermediate(
            job.id, job.user_id, "[Reference] " + character["name"], image, mime
        )
        character["reference_asset_id"] = asset_id
        references[character["id"]] = {
            "data": base64.b64encode(image).decode(),
            "mime_type": mime,
        }
        checkpoint(25 + int(10 * (index + 1) / len(characters)))
    clips = []
    for index, scene in enumerate(scenes):
        selected = [c for c in characters if c["id"] in scene["character_ids"]]
        identity = "\n".join(
            f"{c['name']}: {c['appearance']}; clothes: {c['wardrobe']}; voice: {c['voice']}; language: {c['language']}"
            for c in selected
        )
        scene_prompt = f"""Create a natural cinematic scene with synchronized sound and spoken dialogue. Native clip length up to 10 seconds, at least {scene["duration"]} seconds of usable motion.
Shared continuity: {plan.continuity}
Stable characters (match supplied reference images): {identity}
Scene direction: {scene["description"]}
Speak this exact dialogue in its original language, without added or translated words:
{scene["dialogue"]}
Maintain clothing, faces, objects and setting. No captions or titles. This is scene {index + 1} of {count}.
"""
        generation_params = {
            **params,
            "_reference_images": [references[c["id"]] for c in selected],
        }
        clip, mime = providers.generate(
            "video", model_config["video"], scene_prompt, generation_params
        )
        if not mime.startswith("video/"):
            raise providers.ProviderError("DRAMA_SCENE_INVALID")
        scene["asset_id"] = save_intermediate(
            job.id, job.user_id, "[Scene] " + scene["title"], clip, mime
        )
        clips.append(clip)
        checkpoint(35 + int(40 * (index + 1) / count))
    return assemble(
        clips, duration, aspect, clip_durations=[s["duration"] for s in scenes]
    ), "video/mp4"
