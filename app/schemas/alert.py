from enum import StrEnum

from pydantic import BaseModel


class OpportunitySource(StrEnum):
    CHART = "chart"
    INDICATORS = "indicators"
    FUNDAMENTALS = "fundamentals"
    MIXED = "mixed"


class AlertStatus(StrEnum):
    SIN_OPORTUNIDAD = "SIN_OPORTUNIDAD"
    ALERTA = "ALERTA"
    EN_OBSERVACION = "EN_OBSERVACION"
    CONFIRMADA = "CONFIRMADA"
    INVALIDADA = "INVALIDADA"
    POSIBLE_SENUELO = "POSIBLE_SENUELO"
    COMPRAMOS = "COMPRAMOS"
    NO_COMPRAMOS = "NO_COMPRAMOS"
    WATCHLIST = "WATCHLIST"
    ARCHIVED = "ARCHIVED"


class RiskLevel(StrEnum):
    BAJO = "BAJO 🟢"
    MEDIO = "MEDIO 🟡"
    ALTO = "ALTO 🟠"
    EXTREMO = "EXTREMO 🔴"


class FinalDecision(StrEnum):
    COMPRAMOS = "COMPRAMOS"
    NO_COMPRAMOS = "NO_COMPRAMOS"


class AlertResponse(BaseModel):
    status: str
    ticker: str
    score: int
    risk: RiskLevel
