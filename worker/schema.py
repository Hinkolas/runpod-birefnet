"""Request contract for the background-removal worker.

All job configuration is driven by the request `input`. The image source is pluggable
per request via a discriminated union on `source` (`type: "s3" | "http" | "base64"`),
and so is the optional `destination` (`type: "s3" | "http"`). Without a destination,
results come back inline as base64 in the job output.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

ModelName = Literal["general", "lite", "matting"]


class Output(BaseModel):
    """One requested result image.

    - `mask`   -> 8-bit grayscale alpha mask (white = foreground).
    - `cutout` -> the source image as RGBA with the mask as its alpha channel.
    """

    kind: Literal["mask", "cutout"] = "mask"
    format: Literal["png", "webp"] = "png"
    # webp only: 1-100, higher = better; 100 => lossless. Ignored for png.
    quality: int = Field(default=90, ge=1, le=100)


# --- Source (download) backends -------------------------------------------------


class S3Source(BaseModel):
    type: Literal["s3"]
    bucket: str
    key: str
    endpointUrl: str | None = None   # None => real AWS regional endpoint
    region: str = "auto"
    accessKeyId: str | None = None   # per-request; falls back to worker env
    secretAccessKey: str | None = None


class HttpSource(BaseModel):
    type: Literal["http"]
    url: str                         # may be a presigned GET URL
    headers: dict[str, str] = Field(default_factory=dict)


class Base64Source(BaseModel):
    type: Literal["base64"]
    data: str                        # raw base64, or a data: URL

    @field_validator("data")
    @classmethod
    def _strip_data_url(cls, value: str) -> str:
        return value.split(",", 1)[1] if value.startswith("data:") else value


Source = Annotated[Union[S3Source, HttpSource, Base64Source], Field(discriminator="type")]


# --- Destination (upload) backends ----------------------------------------------


class S3Destination(BaseModel):
    type: Literal["s3"]
    bucket: str
    prefix: str
    endpointUrl: str | None = None
    region: str = "auto"
    accessKeyId: str | None = None
    secretAccessKey: str | None = None


class HttpDestination(BaseModel):
    type: Literal["http"]
    baseUrl: str                     # each output file is PUT to {baseUrl}/{fileName}
    headers: dict[str, str] = Field(default_factory=dict)  # e.g. {"Authorization": "Bearer ..."}


Destination = Annotated[Union[S3Destination, HttpDestination], Field(discriminator="type")]


# --- Top-level job input --------------------------------------------------------


class RemoveBackgroundInput(BaseModel):
    source: Source
    # None => results are returned inline (base64) in the job output.
    destination: Destination | None = None
    model: ModelName = "general"
    # Square inference resolution. BiRefNet is trained at 1024; must be a multiple of 32.
    resolution: int = Field(default=1024, ge=256, le=2048)
    outputs: list[Output] = Field(default_factory=lambda: [Output()], min_length=1)
    # Free-form passthrough, echoed verbatim in the response. Use it to tag a job
    # for usage attribution, e.g. {"app": "app-a", ...}.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("resolution")
    @classmethod
    def _check_resolution(cls, value: int) -> int:
        if value % 32:
            raise ValueError("'resolution' must be a multiple of 32")
        return value

    @model_validator(mode="after")
    def _check_unique_outputs(self) -> "RemoveBackgroundInput":
        names = [f"{o.kind}.{o.format}" for o in self.outputs]
        if len(names) != len(set(names)):
            raise ValueError("Each (kind, format) pair may only be requested once")
        return self
