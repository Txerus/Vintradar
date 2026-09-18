from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
class AlertIn(BaseModel):
    name:str; include_terms:list[str]=Field(default_factory=list); exclude_terms:list[str]=Field(default_factory=list); filters:dict=Field(default_factory=dict)
    min_price:float|None=None; max_price:float|None=None; scan_minutes:int=10; notify_threshold:str="GOOD"; paused:bool=False
class AlertOut(AlertIn):
    id:int; last_scan_at:datetime|None=None
    model_config=ConfigDict(from_attributes=True)
class ListingOut(BaseModel):
    id:int; alert_id:int; external_id:str; title:str; description:str; price:float; shipping_estimate:float; buyer_fee:float; currency:str; url:str; image_url:str|None; condition:str|None; size:str|None; status:str; created_at:datetime; updated_at:datetime
    model_config=ConfigDict(from_attributes=True)
class FlagIn(BaseModel):
    value:bool
class DashboardOut(BaseModel):
    alerts:int; listings:int; active:int; last_scan_at:datetime|None
