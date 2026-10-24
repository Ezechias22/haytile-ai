"""Editable storyboards with stable character/scene IDs and optimistic revisions."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .db import Asset, Job, Project, Session, User
from .main import Generate, current, fail, generate, job_json, limit, wake_worker

router = APIRouter()


class CharacterInput(BaseModel):
    id: str = Field(min_length=8, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    appearance: str = Field(default="", max_length=1000)
    wardrobe: str = Field(default="", max_length=1000)
    voice: str = Field(default="", max_length=500)
    language: str = Field(default="ht", max_length=10)
    reference_asset_id: str | None = None


class SceneInput(BaseModel):
    id: str = Field(min_length=8, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    dialogue: str = Field(default="", max_length=4000)
    duration: int = Field(default=8, ge=1, le=10)
    character_ids: list[str] = Field(default_factory=list, max_length=10)
    asset_id: str | None = None


class Document(BaseModel):
    premise: str = Field(default="", max_length=4000)
    continuity: str = Field(default="", max_length=4000)
    aspect: Literal["16:9", "9:16"] = "16:9"
    characters: list[CharacterInput] = Field(default_factory=list, max_length=20)
    final_asset_id: str | None = None
    scenes: list[SceneInput] = Field(default_factory=list, max_length=22)


class ProjectInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    document: Document
    version: int = Field(default=1, ge=1)


def project_json(p):
    return {
        "id": p.id,
        "title": p.title,
        "document": p.document,
        "version": p.version,
        "created_at": p.created_at,
    }


def validate_document(db, document, user_id):
    ids = [c.id for c in document.characters]
    scenes = [s.id for s in document.scenes]
    if len(ids) != len(set(ids)) or len(scenes) != len(set(scenes)):
        fail("DUPLICATE_STORYBOARD_ID")
    if sum(s.duration for s in document.scenes) > 180:
        fail("VIDEO_DURATION_INVALID")
    for scene in document.scenes:
        if set(scene.character_ids) - set(ids):
            fail("CHARACTER_REFERENCE_INVALID")
    for aid, mime in (
        [(document.final_asset_id, "video/")]
        + [(c.reference_asset_id, "image/") for c in document.characters]
        + [(s.asset_id, "video/") for s in document.scenes]
    ):
        if aid:
            asset = db.get(Asset, aid)
            if not asset or asset.user_id != user_id or not asset.mime.startswith(mime):
                fail("REFERENCE_INVALID")


@router.get("/v1/projects")
def list_projects(user=Depends(current)):
    with Session() as db:
        return [
            project_json(p)
            for p in db.scalars(
                select(Project)
                .where(Project.user_id == user.id)
                .order_by(Project.created_at.desc())
                .limit(100)
            )
        ]


@router.post("/v1/projects", status_code=201)
def create_project(body: ProjectInput, user=Depends(current)):
    limit("projects:" + user.id, 30, 3600)
    with Session.begin() as db:
        validate_document(db, body.document, user.id)
        p = Project(
            user_id=user.id, title=body.title, document=body.document.model_dump()
        )
        db.add(p)
        db.flush()
        return project_json(p)


@router.put("/v1/projects/{project_id}")
def update_project(project_id: str, body: ProjectInput, user=Depends(current)):
    with Session.begin() as db:
        p = db.scalar(
            select(Project)
            .where(Project.id == project_id, Project.user_id == user.id)
            .with_for_update()
        )
        if not p:
            fail("NOT_FOUND", 404)
        if p.version != body.version:
            fail("PROJECT_REVISION_CONFLICT", 409)
        validate_document(db, body.document, user.id)
        p.title = body.title
        p.document = body.document.model_dump()
        p.version += 1
        return project_json(p)


@router.delete("/v1/projects/{project_id}")
def remove_project(project_id: str, user=Depends(current)):
    with Session.begin() as db:
        p = db.scalar(
            select(Project)
            .where(Project.id == project_id, Project.user_id == user.id)
            .with_for_update()
        )
        if not p:
            fail("NOT_FOUND", 404)
        db.delete(p)
    return {"ok": True}


class SceneGeneration(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    confirmed_credits: int = Field(ge=0)


@router.post("/v1/projects/{project_id}/scenes/{scene_id}/generate", status_code=202)
def render_scene(
    project_id: str, scene_id: str, body: SceneGeneration, user=Depends(current)
):
    with Session() as db:
        project = db.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == user.id)
        )
        if not project:
            fail("NOT_FOUND", 404)
        doc = Document.model_validate(project.document)
        scene = next((s for s in doc.scenes if s.id == scene_id), None)
        if not scene:
            fail("NOT_FOUND", 404)
        chars = [c for c in doc.characters if c.id in scene.character_ids]
        prompt = (
            f"{doc.premise}\nContinuity: {doc.continuity}\nScene: {scene.description}\n"
        )
        for char in chars:
            prompt += f"Character {char.id} {char.name}: {char.appearance}; wardrobe: {char.wardrobe}; voice: {char.voice}; language: {char.language}\n"
        prompt += (
            "Dialogue must follow this exact script, without translation or added words:\n"
            + scene.dialogue
        )
        params = {
            "aspect": doc.aspect,
            "duration": max(8, scene.duration),
            "project_id": project.id,
            "scene_id": scene.id,
        }
        if chars and chars[0].reference_asset_id:
            params["reference_asset_id"] = chars[0].reference_asset_id
    return generate(
        Generate(
            studio="video",
            title=scene.title,
            prompt=prompt,
            params=params,
            confirmed_credits=body.confirmed_credits,
            idempotency_key=body.idempotency_key,
        ),
        user,
    )


class Assembly(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)


@router.post("/v1/projects/{project_id}/assemble", status_code=202)
def assemble_project(project_id: str, body: Assembly, user=Depends(current)):
    limit("assemble:" + user.id, 10, 3600)
    with Session.begin() as db:
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        p = db.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == user.id)
        )
        if not p:
            fail("NOT_FOUND", 404)
        old = db.scalar(
            select(Job).where(
                Job.user_id == user.id, Job.idempotency_key == body.idempotency_key
            )
        )
        if old:
            if old.studio != "assembly" or old.params.get("project_id") != project_id:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return job_json(old)
        doc = Document.model_validate(p.document)
        duration = sum(s.duration for s in doc.scenes)
        if not 8 <= duration <= 180:
            fail("VIDEO_DURATION_INVALID")
        for scene in doc.scenes:
            asset = db.get(Asset, scene.asset_id) if scene.asset_id else None
            if (
                not asset
                or asset.user_id != user.id
                or not asset.mime.startswith("video/")
            ):
                fail("SCENE_MEDIA_NOT_READY", 409)
        pending = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.user_id == user.id,
                Job.status.in_(["queued", "processing", "quality_check"]),
            )
        )
        if pending >= 3:
            fail("TOO_MANY_JOBS", 429)
        job = Job(
            user_id=user.id,
            title=p.title,
            studio="assembly",
            prompt=doc.premise,
            idempotency_key=body.idempotency_key,
            credits=0,
            params={
                "project_id": p.id,
                "input_params": {
                    "duration": duration,
                    "aspect": doc.aspect,
                    "clip_ids": [s.asset_id for s in doc.scenes],
                    "clip_durations": [s.duration for s in doc.scenes],
                },
            },
        )
        db.add(job)
        db.flush()
        result = job_json(job)
    wake_worker()
    return result
