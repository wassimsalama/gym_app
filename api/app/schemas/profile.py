from typing import Literal

from pydantic import BaseModel, ConfigDict

#: The two display units the app supports. Storage stays kg everywhere (spec §5);
#: this only decides what the user is shown.
UnitName = Literal["kg", "lb"]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: UnitName
