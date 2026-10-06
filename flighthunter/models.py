"""Modèles de données partagés (pydantic v2)."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Baggage(str, Enum):
    CHECKED_REQUIRED = "checked_required"  # soute obligatoire
    CABIN_ONLY = "cabin_only"              # cabine seul
    ANY = "any"                            # peu importe (coût du bagage ajouté au comparatif)


class RouteType(str, Enum):
    THROUGH = "through"            # un seul billet
    SELF_TRANSFER = "self_transfer"  # billets séparés
    POSITIONING = "positioning"    # vol de positionnement + long-courrier séparé
    OPEN_JAW = "open_jaw"          # aller/retour sur aéroports différents
    HIDDEN_CITY = "hidden_city"    # cabine seule, ToS risqué
    MULTI_LEG = "multi_leg"        # chaîne extrême : train transfrontalier + vols low-cost + attente au hub


class LegKind(str, Enum):
    GROUND = "ground"   # train / bus / navette
    FLIGHT = "flight"   # segment aérien


class Leg(BaseModel):
    kind: LegKind
    frm: str
    to: str
    mode: str = ""             # carrier ou moyen de transport
    price_eur: float = 0.0
    duration_min: int = 0
    wait_nights: int = 0       # attente délibérée à `to` avant le leg suivant (ex. capter un vol régional)


class Techniques(BaseModel):
    through_fare: bool = True
    self_transfer: bool = False
    positioning: bool = False
    open_jaw: bool = False
    ground_multimodal: bool = False
    hidden_city: bool = False
    pos_currency_arbitrage: bool = False
    error_fares: bool = False
    free_stopover: bool = False
    extreme_multileg: bool = False   # active le moteur de chaînes extrêmes (train+low-cost+attente hub)


class HubWait(BaseModel):
    min_nights: int = 0
    max_nights: int = 3


class Extreme(BaseModel):
    """Paramètres du moteur de chaînes extrêmes (multi-legs)."""
    max_flight_legs: int = 3
    max_total_transit_hours: int = 60      # plafond du temps EN TRANSIT (hors attente délibérée)
    min_layover_hours: float = 2.5
    allow_cross_border_ground: bool = True  # autoriser train/bus vers un autre pays
    hub_wait: HubWait = Field(default_factory=HubWait)
    accommodation_eur_per_night: float = 30.0
    baggage_eur_per_flight_leg: float = 45.0
    date_samples: int = 6                  # nb de dates de départ échantillonnées


class Stay(BaseModel):
    min_nights: int = 7
    max_nights: int = 30
    maximize: bool = False


class NotifyPrefs(BaseModel):
    email: bool = True
    telegram: bool = True


class Alert(BaseModel):
    name: str
    enabled: bool = True
    origins: list[str]
    destination: str
    depart_earliest: date
    depart_latest: date
    return_earliest: date
    return_latest: date
    stay: Stay = Field(default_factory=Stay)
    date_step_days: int = 3
    max_price_eur: float = 800.0
    currency: str = "EUR"
    baggage: Baggage = Baggage.ANY
    techniques: Techniques = Field(default_factory=Techniques)
    extreme: Extreme = Field(default_factory=Extreme)
    notify: NotifyPrefs = Field(default_factory=NotifyPrefs)


class DealItem(BaseModel):
    """Un deal / erreur de prix issu d'un flux communautaire (non structuré en prix)."""
    title: str
    url: str
    source: str
    published: str = ""
    snippet: str = ""
    matched: str = ""   # mot-clé qui a déclenché la pertinence


class GroundAccess(BaseModel):
    """Trajet sol pour rejoindre l'aéroport de départ (multimodal)."""
    airport: str
    mode: str
    cost_eur: float
    duration_min: int


class FlightOption(BaseModel):
    """Une option de voyage complète, comparable en prix net porte-à-porte."""
    origin: str
    destination: str
    outbound_date: date
    return_date: Optional[date] = None
    return_airport: Optional[str] = None      # != origin si open-jaw

    route_type: RouteType = RouteType.THROUGH
    hubs: list[str] = Field(default_factory=list)
    carriers: list[str] = Field(default_factory=list)

    price_eur: float                          # prix billet(s) avion
    baggage_included: bool = False
    baggage_addon_eur: float = 0.0            # coût soute à ajouter si non inclus

    ground: Optional[GroundAccess] = None     # accès sol simple (multimodal, options non multi-leg)
    stay_nights: Optional[int] = None

    # Chaînes extrêmes (MULTI_LEG) :
    legs: list[Leg] = Field(default_factory=list)
    extra_costs_eur: float = 0.0              # sol + hébergement d'attente déjà agrégés dans les legs
    extra_costs_label: str = ""
    total_transit_min: Optional[int] = None   # temps en transit (hors attente délibérée)
    wait_nights: int = 0                      # nuits d'attente au hub (capter le vol régional)

    source: str = "unknown"
    booking_url: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)

    # Rempli par la couche pricing :
    net_price_eur: Optional[float] = None     # tout compris, après cashback/bagage/sol/risque
    cashback_eur: float = 0.0
    risk_cost_eur: float = 0.0                # espérance de coût-risque (retard/rebillet/fiabilité)
    is_error_fare: bool = False

    # Réservation anticipée :
    days_to_departure: Optional[int] = None
    booking_reco: str = ""                    # recommandation "réserver tôt / au plus bas / attendre"

    def signature(self) -> str:
        """Identité stable d'une offre pour la déduplication des alertes."""
        rt = self.return_date.isoformat() if self.return_date else "oneway"
        path = "/".join(self.hubs)
        extra = f"-w{self.wait_nights}" if self.route_type == RouteType.MULTI_LEG else ""
        return (
            f"{self.origin}-{self.destination}-{self.outbound_date.isoformat()}-{rt}"
            f"-{self.route_type.value}-{path}{extra}"
        )
