import logging
import re
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# Standard estimation parameters for Germany -> Italy vehicle import
DEFAULT_BISARCA_EUR = 750              # Insured car carrier transport DE -> Northern/Central Italy
DEFAULT_NAZIONALIZZAZIONE_EUR = 1050   # Agency fees, Agenzia Entrate chassis registration (F24 VAT), Single Document (DU) and plates
DEFAULT_IPT_PHEV_EUR = 350             # Reduced provincial registration tax (IPT) for PHEVs (calculated on thermal engine power)
DEFAULT_IPT_STANDARD_EUR = 550         # Standard IPT for mid-size ICE vehicles


def is_phev_model(model_str: Optional[str]) -> bool:
    """Checks whether the vehicle model indicates a plug-in hybrid (e.g. BMW 330e, PHEV)."""
    if not model_str:
        return True  # Project focus is BMW 330e, defaults to True unless specified otherwise
    lower = model_str.lower()
    return any(p in lower for p in ("330e", "phev", "plug-in", "plugin", "hybrid", "ibrid", "b48"))


def calculate_import_tco(
    price_eur: Union[int, float, str, None],
    car_model: Optional[str] = None,
    seller_country: Optional[str] = "DE",
    power_kw: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Calculates estimated turn-key import expenses for bringing a vehicle from Germany to Italy.

    Breakdown:
    1. Insured carrier transport (~750 EUR)
    2. Registration agency, tax clearance, Single Vehicle Document (DU) and new license plates (~1,050 EUR)
    3. IPT provincial registration tax (~350 EUR for PHEV thermal power)
    4. Luxury tax (Superbollo): 0 EUR for PHEV (BMW 330e thermal engine is 135 kW / 184 hp, below 185 kW threshold)

    Returns a detailed breakdown dictionary and total on-the-road estimated price.
    """
    if price_eur is None:
        return None

    try:
        if isinstance(price_eur, str):
            clean_str = re.sub(r"[^\d.]", "", price_eur.replace(",", "."))
            # Se ci sono più punti o formattazione europea tipo 34.900
            if "." in clean_str and len(clean_str.split(".")[-1]) == 3:
                clean_str = clean_str.replace(".", "")
            base_price = int(float(clean_str))
        else:
            base_price = int(float(price_eur))
    except (ValueError, TypeError):
        return None

    if base_price <= 0:
        return None

    phev = is_phev_model(car_model)
    ipt_cost = DEFAULT_IPT_PHEV_EUR if phev else DEFAULT_IPT_STANDARD_EUR

    # Calcolo Superbollo: per PHEV si considerano SOLO i kW del motore termico (135 kW per B48)
    superbollo = 0
    if not phev and power_kw and power_kw > 185:
        superbollo = (power_kw - 185) * 20

    spese_totali = DEFAULT_BISARCA_EUR + DEFAULT_NAZIONALIZZAZIONE_EUR + ipt_cost + superbollo
    prezzo_finito = base_price + spese_totali

    superbollo_note = (
        "Superbollo ESENTE (motore termico 135 kW / 184 CV < soglia 185 kW)"
        if phev
        else (f"{superbollo} €/anno" if superbollo > 0 else "0 €")
    )

    return {
        "prezzo_base_eur": base_price,
        "spese_import_totale_eur": spese_totali,
        "prezzo_finito_eur": prezzo_finito,
        "is_phev": phev,
        "superbollo_esente": (superbollo == 0),
        "dettaglio": {
            "bisarca_eur": DEFAULT_BISARCA_EUR,
            "nazionalizzazione_targhe_eur": DEFAULT_NAZIONALIZZAZIONE_EUR,
            "ipt_immatricolazione_eur": ipt_cost,
            "superbollo_eur": superbollo,
            "note_fiscali": superbollo_note,
        },
    }

