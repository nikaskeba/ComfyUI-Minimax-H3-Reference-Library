import io
import uuid
from pathlib import Path

import av
from aiohttp import web
from PIL import Image, ImageOps, UnidentifiedImageError

from comfy_extras.nodes_audio import load as load_audio_file
from server import PromptServer

from .library import (
    audio_directory,
    create_record,
    delete_record,
    get_record,
    image_directory,
    list_records,
    media_path,
    remove_media,
    update_record,
    video_directory,
)
from .built_in_references import catalog_revision, list_built_in_references


WEB_DIRECTORY_PATH = Path(__file__).parent / "manager"
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".mp4", ".ogg", ".opus", ".wav", ".webm"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"}
ROUTES_REGISTERED = False


def register_routes():
    global ROUTES_REGISTERED
    if ROUTES_REGISTERED:
        return
    ROUTES_REGISTERED = True
    routes = PromptServer.instance.routes

    @routes.get("/h3-references")
    async def manager_page(request):
        return web.FileResponse(WEB_DIRECTORY_PATH / "index.html")

    @routes.get("/h3-built-in-references")
    async def built_in_page(request):
        return web.FileResponse(WEB_DIRECTORY_PATH / "built-ins.html")

    @routes.get("/h3-references/static/{filename}")
    async def manager_asset(request):
        filename = request.match_info["filename"]
        if filename not in {"manager.css", "manager.js"}:
            raise web.HTTPNotFound()
        return web.FileResponse(WEB_DIRECTORY_PATH / filename)

    @routes.get("/h3-built-in-references/static/{filename}")
    async def built_in_asset(request):
        filename = request.match_info["filename"]
        if filename not in {"built-ins.css", "built-ins.js"}:
            raise web.HTTPNotFound()
        return web.FileResponse(WEB_DIRECTORY_PATH / filename)

    @routes.get("/api/h3-references/records")
    async def get_records(request):
        records = sorted(list_records(), key=lambda record: record["tag"].lower())
        categories = sorted({record.get("category") or "other" for record in records})
        return web.json_response({
            "records": [_public_record(record) for record in records],
            "categories": categories,
        })

    @routes.get("/api/h3-built-in-references/records")
    async def get_built_ins(request):
        try:
            records = sorted(
                list_built_in_references(),
                key=lambda record: (record["folder"], record["name"].lower()),
            )
            return web.json_response({
                "revision": catalog_revision(),
                "records": [
                    {key: value for key, value in record.items() if key != "clips"}
                    for record in records
                ],
            })
        except (OSError, ValueError) as error:
            return web.json_response({"error": str(error)}, status=500)

    @routes.post("/api/h3-references/records")
    async def add_record(request):
        image_filename = audio_filename = video_filename = None
        try:
            fields, files = await _read_multipart(request)
            if "image" in files:
                image_filename = _save_image(*files["image"])
            if "audio" in files:
                audio_filename = _save_audio(*files["audio"])
            video_has_audio = False
            if "video" in files:
                video_filename, video_has_audio = _save_video(*files["video"])
            record = create_record(
                tag=fields.get("tag"),
                category=fields.get("category", "other"),
                image_description=fields.get("image_description"),
                audio_description=fields.get("audio_description"),
                image_file=image_filename,
                audio_file=audio_filename,
                reference_type=fields.get("reference_type", "uncategorized"),
                video_description=fields.get("video_description"),
                video_file=video_filename,
                video_has_audio=video_has_audio,
            )
            return web.json_response({"record": _public_record(record)}, status=201)
        except Exception as error:
            remove_media(image_filename, "image")
            remove_media(audio_filename, "audio")
            remove_media(video_filename, "video")
            return _error_response(error)

    @routes.put("/api/h3-references/records/{record_id}")
    async def edit_record(request):
        record_id = request.match_info["record_id"]
        image_filename = audio_filename = video_filename = None
        try:
            fields, files = await _read_multipart(request)
            current = get_record(record_id)
            if "image" in files:
                image_filename = _save_image(*files["image"])
            if "audio" in files:
                audio_filename = _save_audio(*files["audio"])
            video_has_audio = None
            if "video" in files:
                video_filename, video_has_audio = _save_video(*files["video"])
            record, old_image, old_audio, old_video = update_record(
                record_id=record_id,
                tag=fields.get("tag", current["tag"]),
                category=fields.get("category", current.get("category", "other")),
                image_description=fields.get("image_description", current.get("image_description", "")),
                audio_description=fields.get("audio_description", current.get("audio_description", "")),
                image_file=image_filename,
                audio_file=audio_filename,
                remove_image=fields.get("remove_image") == "true",
                remove_audio=fields.get("remove_audio") == "true",
                reference_type=fields.get(
                    "reference_type", current.get("reference_type", "uncategorized")),
                video_description=fields.get("video_description", current.get("video_description", "")),
                video_file=video_filename,
                video_has_audio=video_has_audio,
                remove_video=fields.get("remove_video") == "true",
            )
            remove_media(old_image, "image")
            remove_media(old_audio, "audio")
            remove_media(old_video, "video")
            return web.json_response({"record": _public_record(record)})
        except Exception as error:
            remove_media(image_filename, "image")
            remove_media(audio_filename, "audio")
            remove_media(video_filename, "video")
            return _error_response(error)

    @routes.delete("/api/h3-references/records/{record_id}")
    async def remove_record(request):
        try:
            record = delete_record(request.match_info["record_id"])
            remove_media(record.get("image_file"), "image")
            remove_media(record.get("audio_file"), "audio")
            remove_media(record.get("video_file"), "video")
            return web.json_response({"deleted": record["id"]})
        except Exception as error:
            return _error_response(error)

    @routes.get("/api/h3-references/records/{record_id}/media/{kind}")
    async def get_media(request):
        try:
            record = get_record(request.match_info["record_id"])
            return web.FileResponse(media_path(record, request.match_info["kind"]))
        except (KeyError, FileNotFoundError, ValueError):
            raise web.HTTPNotFound()


async def _read_multipart(request):
    if request.content_type == "application/x-www-form-urlencoded":
        posted = await request.post()
        return {key: str(value).strip() for key, value in posted.items()}, {}
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="Expected form data.")
    fields = {}
    files = {}
    reader = await request.multipart()
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.filename:
            files[part.name] = (part.filename, await part.read(decode=False))
        else:
            fields[part.name] = (await part.text()).strip()
    return fields, files


def _save_image(filename, data):
    if not data:
        raise ValueError("Uploaded image is empty.")
    image_directory().mkdir(parents=True, exist_ok=True)
    output_name = f"{uuid.uuid4().hex}.png"
    target = image_directory() / output_name
    temporary = target.with_suffix(".tmp")
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.save(temporary, format="PNG")
        with Image.open(temporary) as check:
            check.verify()
        temporary.replace(target)
        return output_name
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"'{filename}' is not a valid image.") from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _save_audio(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise ValueError(f"'{filename}' is not a supported audio file.")
    if not data:
        raise ValueError("Uploaded audio is empty.")
    audio_directory().mkdir(parents=True, exist_ok=True)
    output_name = f"{uuid.uuid4().hex}{suffix}"
    target = audio_directory() / output_name
    temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
    try:
        temporary.write_bytes(data)
        load_audio_file(str(temporary))
        temporary.replace(target)
        return output_name
    except (OSError, ValueError, RuntimeError) as error:
        raise ValueError(f"'{filename}' is not a valid audio file.") from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _save_video(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise ValueError(f"'{filename}' is not a supported video file.")
    if not data:
        raise ValueError("Uploaded video is empty.")
    try:
        with av.open(io.BytesIO(data), mode="r") as container:
            if not container.streams.video:
                raise ValueError(f"'{filename}' does not contain a video track.")
            has_audio = bool(container.streams.audio)
    except (OSError, ValueError, av.FFmpegError) as error:
        if isinstance(error, ValueError) and "does not contain" in str(error):
            raise
        raise ValueError(f"'{filename}' is not a valid video file.") from error

    video_directory().mkdir(parents=True, exist_ok=True)
    output_name = f"{uuid.uuid4().hex}{suffix}"
    target = video_directory() / output_name
    temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
    try:
        temporary.write_bytes(data)
        temporary.replace(target)
        return output_name, has_audio
    finally:
        if temporary.exists():
            temporary.unlink()


def _public_record(record):
    record_id = record["id"]
    return {
        "id": record_id,
        "tag": record["tag"],
        "category": record.get("category", "other"),
        "reference_type": record.get("reference_type", "uncategorized"),
        "image_description": record.get("image_description", ""),
        "audio_description": record.get("audio_description", ""),
        "video_description": record.get("video_description", ""),
        "has_image": bool(record.get("image_file")),
        "has_audio": bool(record.get("audio_file")),
        "has_video": bool(record.get("video_file")),
        "has_video_audio": bool(record.get("video_file") and record.get("video_has_audio")),
        "image_url": f"/api/h3-references/records/{record_id}/media/image" if record.get("image_file") else None,
        "audio_url": f"/api/h3-references/records/{record_id}/media/audio" if record.get("audio_file") else None,
        "video_url": f"/api/h3-references/records/{record_id}/media/video" if record.get("video_file") else None,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _error_response(error):
    if isinstance(error, web.HTTPException):
        message = (error.text or error.reason or "Upload request failed.").strip()
        return web.json_response({"error": message}, status=error.status)
    if isinstance(error, KeyError):
        return web.json_response({"error": "Reference record was not found."}, status=404)
    if isinstance(error, (ValueError, FileNotFoundError)):
        return web.json_response({"error": str(error)}, status=400)
    return web.json_response({"error": f"Reference library error: {error}"}, status=500)
