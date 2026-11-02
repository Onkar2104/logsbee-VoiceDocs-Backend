from pydantic import BaseModel, ConfigDict


class LogsbeeRole(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    is_system_role: bool


class LogsbeeAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    is_active: bool
    is_deleted: bool


class LogsbeeProduct(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    code: str
    name: str


class LogsbeeUserContext(BaseModel):
    """Authenticated user context returned by Logsbee User Management."""

    model_config = ConfigDict(extra="ignore")

    id: str
    account_id: str | None = None
    first_name: str
    last_name: str
    email: str
    contact: str | None = None
    is_email_verified: bool
    is_contact_verified: bool
    is_two_factor_authenticated: bool
    role: LogsbeeRole | None = None
    permission_codes: list[str] = []
    account: LogsbeeAccount | None = None
    products: list[LogsbeeProduct] = []
