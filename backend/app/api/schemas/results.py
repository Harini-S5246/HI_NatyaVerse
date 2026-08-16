from pydantic import BaseModel


class ResultListItem(BaseModel):
    result_id: str
