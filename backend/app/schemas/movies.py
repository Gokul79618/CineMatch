"""Validated catalog records and movie API request/response contracts."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MovieCatalogRecord(BaseModel):
    """A source record used to seed the local catalog."""

    model_config = ConfigDict(extra="forbid")

    movie_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=1, max_length=50)
    genres: list[str] = Field(min_length=1, max_length=12)
    release_year: int = Field(ge=1888, le=2100)
    runtime_minutes: int | None = Field(default=None, ge=1, le=600)
    overview: str = Field(min_length=1, max_length=1000)
    rating: float | None = Field(default=None, ge=0, le=10)
    source_url: str = Field(min_length=1, max_length=500)

    @field_validator("movie_id", "title", "language", "overview", "source_url")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("source_url")
    @classmethod
    def require_https_source(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("source_url must use HTTPS")
        return value

    @field_validator("genres")
    @classmethod
    def normalize_genres(cls, genres: list[str]) -> list[str]:
        normalized = [genre.strip() for genre in genres]
        if any(not genre for genre in normalized):
            raise ValueError("genres must not contain blank values")
        if len({genre.casefold() for genre in normalized}) != len(normalized):
            raise ValueError("genres must be unique")
        return normalized


class Movie(BaseModel):
    movie_id: str
    title: str
    language: str
    genres: list[str]
    release_year: int
    runtime_minutes: int | None
    overview: str
    rating: float | None
    source_url: str


class MovieSearchRequest(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=50)
    genre: str | None = Field(default=None, max_length=80)
    release_year: int | None = Field(default=None, ge=1888, le=2100)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("query", "language", "genre", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = " ".join(value.split())
            return value or None
        return value


class MovieFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, max_length=50)
    genre: str | None = Field(default=None, max_length=80)
    min_year: int | None = Field(default=None, ge=1888, le=2100)
    max_year: int | None = Field(default=None, ge=1888, le=2100)
    min_runtime: int | None = Field(default=None, ge=1, le=600)
    max_runtime: int | None = Field(default=None, ge=1, le=600)
    min_rating: float | None = Field(default=None, ge=0, le=10)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("language", "genre", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = " ".join(value.split())
            return value or None
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "MovieFilterRequest":
        if self.min_year is not None and self.max_year is not None:
            if self.min_year > self.max_year:
                raise ValueError("min_year must not exceed max_year")
        if self.min_runtime is not None and self.max_runtime is not None:
            if self.min_runtime > self.max_runtime:
                raise ValueError("min_runtime must not exceed max_runtime")
        return self


class MovieResults(BaseModel):
    count: int
    limit: int
    items: list[Movie]


class MovieIdRequest(BaseModel):
    movie_id: str = Field(min_length=1, max_length=100)

    @field_validator("movie_id")
    @classmethod
    def normalize_movie_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("movie_id must not be blank")
        return normalized


class MovieStats(BaseModel):
    total_movies: int
    distinct_languages: int
    distinct_genres: int
    missing_runtime: int
    missing_rating: int
