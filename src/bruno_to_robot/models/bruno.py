"""Pydantic models for Bruno collection data."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class AuthType(str, Enum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api-key"
    OAUTH2 = "oauth2"
    INHERIT = "inherit"
    CERT = "cert"


class BodyType(str, Enum):
    JSON = "json"
    TEXT = "text"
    XML = "xml"
    FORM = "form"
    MULTIPART = "multipart"
    GRAPHQL = "graphql"
    NONE = "none"


class BrunoAuth(BaseModel):
    """Authentication configuration."""

    type: AuthType = AuthType.NONE
    username: str | None = None
    password: str | None = None
    token: str | None = None
    api_key: str | None = None
    api_key_name: str | None = None  # Header name or query param
    api_key_location: str | None = None  # "header" or "query"
    cert_path: str | None = None
    key_path: str | None = None


class BrunoBody(BaseModel):
    """Request body configuration."""

    type: BodyType = BodyType.NONE
    data: str | dict[str, Any] | None = None
    raw: str | None = None  # For raw text/xml


class BrunoScript(BaseModel):
    """Pre/post request script."""

    type: str  # "pre-request", "post-request", "tests"
    code: str
    enabled: bool = True


class BrunoHttp(BaseModel):
    """HTTP request configuration."""

    method: HttpMethod = HttpMethod.GET
    url: str
    body: BrunoBody | None = None
    auth: AuthType = AuthType.INHERIT
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)  # Query params


class BrunoRequest(BaseModel):
    """Single Bruno request (OpenCollection format)."""

    name: str
    type: str = "http"
    seq: int = 1
    http: BrunoHttp
    runtime: BrunoRuntime | None = None
    settings: BrunoSettings | None = None
    # For folder structure
    path: str | None = None  # Relative path in collection


class BrunoRuntime(BaseModel):
    """Runtime scripts configuration."""

    scripts: list[BrunoScript] = Field(default_factory=list)


class BrunoSettings(BaseModel):
    """Request settings."""

    encode_url: bool = True
    timeout: int | None = None


class BrunoVariable(BaseModel):
    """Collection/folder level variable."""

    name: str
    value: str | int | float | bool | None
    secret: bool = False
    enabled: bool = True


class BrunoFolder(BaseModel):
    """Folder in Bruno collection."""

    name: str
    path: str
    requests: list[BrunoRequest] = Field(default_factory=list)
    folders: list[BrunoFolder] = Field(default_factory=list)
    variables: list[BrunoVariable] = Field(default_factory=list)


class BrunoCollection(BaseModel):
    """Root Bruno collection (OpenCollection format).."""

    name: str
    version: str = "1.0"
    variables: list[BrunoVariable] = Field(default_factory=list)
    auth: BrunoAuth | None = None
    base_url: str | None = None
    folders: list[BrunoFolder] = Field(default_factory=list)
    requests: list[BrunoRequest] = Field(default_factory=list)  # Root level requests
