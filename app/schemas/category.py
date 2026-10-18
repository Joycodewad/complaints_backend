from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    is_active: bool = True


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(None, min_length=2, max_length=120)
    description: str | None = None
    is_active: bool | None = None


class CategoryOut(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
