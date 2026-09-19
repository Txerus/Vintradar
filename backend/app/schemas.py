from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
class AlertIn(BaseModel):
    name:str=Field(min_length=1,max_length=160); include_terms:list[str]=Field(default_factory=list); exclude_terms:list[str]=Field(default_factory=list); filters:dict=Field(default_factory=dict)
    min_price:float|None=Field(default=None,ge=0); max_price:float|None=Field(default=None,ge=0); scan_minutes:int=Field(default=10,ge=1,le=1440); notify_threshold:str=Field(default="GOOD",pattern="^(DEAL|GOOD|NORMAL)$"); paused:bool=False

    @model_validator(mode="after")
    def prices_are_ordered(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be lower than or equal to max_price")
        return self
class AlertOut(AlertIn):
    id:int; last_scan_at:datetime|None=None
    model_config=ConfigDict(from_attributes=True)
class ListingOut(BaseModel):
    id:int; alert_id:int; external_id:str; title:str; description:str; price:float; shipping_estimate:float; buyer_fee:float; currency:str; url:str; image_url:str|None; image_urls:list[str]; seller_name:str|None; seller_rating:float|None; seller_reviews_count:int|None; condition:str|None; size:str|None; score_label:str|None; score_percentile:float|None; score_median:float|None; score_sample_count:int; score_confidence:str|None; status:str; created_at:datetime; updated_at:datetime
    model_config=ConfigDict(from_attributes=True)
class FlagIn(BaseModel):
    value:bool
class FlagOut(BaseModel):
    listing_id:int; favorite:bool=False; seen:bool=False; hidden:bool=False
    model_config=ConfigDict(from_attributes=True)
class SnapshotOut(BaseModel):
    id:int; listing_id:int; price:float; status:str; observed_at:datetime
    model_config=ConfigDict(from_attributes=True)
class DashboardOut(BaseModel):
    alerts:int; listings:int; active:int; last_scan_at:datetime|None
