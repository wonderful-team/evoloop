from typing import Literal

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.id import gen_uuid
from app.domain.planning.schemas import Step, Plan
