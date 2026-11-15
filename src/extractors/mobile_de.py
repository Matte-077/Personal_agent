import json
import logging
import re
from typing import Dict, Any, Optional, List
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MOBILE_DE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,it;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Upgrade-Insecure-Requests": "1",
}


def parse_mobile_de_html(html_content: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Estrae i dettagli di un annuncio auto mobile.de da HTML, cercando prima nei dati strutturati
    JSON-LD (Schema.org) e poi nei metadati OpenGraph e classi specifiche.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    title: Optional[str] = None
    price_eur: Optional[int] = None
    mileage_km: Optional[int] = None
    first_registration: Optional[str] = None
    fuel_type: Optional[str] = None
    power_kw_hp: Optional[str] = None
    features: List[str] = []
    seller_location: Optional[str] = None
    description: Optional[str] = None
    images: List[str] = []

    # 1. Parsing JSON-LD strutturato
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string or "{}")
            items_to_check = data if isinstance(data, list) else [data]
            for item in items_to_check:
                item_type = item.get("@type", "")
                if item_type in ("Car", "Vehicle", "Product"):
                    if not title and "name" in item:
                        title = item["name"]
                    if not description and "description" in item:
                        description = item["description"]
                    if "image" in item:
                        raw_imgs = item["image"]
                        if isinstance(raw_imgs, list):
                            for img in raw_imgs:
                                img_url = img.get("url") if isinstance(img, dict) else str(img)
                                if img_url and img_url.startswith("http") and img_url not in images:
                                    images.append(img_url)
                        elif isinstance(raw_imgs, str) and raw_imgs.startswith("http") and raw_imgs not in images:
                            images.append(raw_imgs)
                    if "offers" in item:
                        offer = item["offers"]
                        if isinstance(offer, list):
                            offer = offer[0]
                        if isinstance(offer, dict) and "price" in offer:
                            try:
                                price_eur = int(float(str(offer["price"]).replace(",", ".")))
                            except (ValueError, TypeError):
                                pass
                    if "mileageFromOdometer" in item:
                        val = item["mileageFromOdometer"]
                        if isinstance(val, dict) and "value" in val:
                            val = val["value"]
                        try:
                            mileage_km = int(re.sub(r"[^\d]", "", str(val)))
                        except (ValueError, TypeError):
                            pass
                    if "dateVehicleFirstRegistered" in item:
                        first_registration = str(item["dateVehicleFirstRegistered"])
                    if "fuelType" in item:
                        fuel_type = str(item["fuelType"])
                    if "vehicleEngine" in item:
                        eng = item["vehicleEngine"]
                        if isinstance(eng, dict) and "enginePower" in eng:
                            power_kw_hp = str(eng["enginePower"])
                        elif isinstance(eng, str):
                            power_kw_hp = eng
                    if "seller" in item:
                        sel = item["seller"]
                        if isinstance(sel, dict):
                            addr = sel.get("address")
                            if isinstance(addr, dict):
                                seller_location = f"{addr.get('addressLocality', '')} {addr.get('addressCountry', '')}".strip()
                            elif isinstance(addr, str):
                                seller_location = addr
        except Exception as e:
            logger.debug(f"Errore parsing blocco JSON-LD: {e}")

    # 2. Fallback e arricchimento immagini da OpenGraph e tag HTML
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        og_img_url = og_image["content"]
        if og_img_url.startswith("http") and og_img_url not in images:
            images.insert(0, og_img_url)

    # Scan additional gallery img tags
    for img_tag in soup.find_all("img"):
        src = img_tag.get("data-src") or img_tag.get("src") or img_tag.get("data-lazy-src")
        if src and src.startswith("http") and not any(x in src.lower() for x in [".svg", ".gif", "icon", "logo"]):
            # Ebayimg / classistatic images can often be expanded by stripping thumbnail params
            if ("ebayimg.com" in src or "classistatic" in src or "mobile.de" in src) and src not in images:
                images.append(src)

    # Fallback to OpenGraph and HTML title tags
    if not title:
        og_title = soup.find("meta", property="og:title")
        title = og_title.get("content") if og_title else (soup.title.string if soup.title else None)

    if not description:
        og_desc = soup.find("meta", property="og:description")
        description = og_desc.get("content") if og_desc else None

    # Search options and equipment (e.g. laser, hitch, HUD) in listing text
    page_text = soup.get_text()
    if not power_kw_hp:
        power_match = re.search(r"(\d{2,3}\s*kW\s*(?:\(\d{2,3}\s*PS\))?|\d{2,3}\s*PS|\d{2,3}\s*CV)", page_text)
        if power_match:
            power_kw_hp = power_match.group(0).strip()

    if not seller_location:
        loc_match = re.search(r"\b(\d{5}\s+[A-Za-zäöüß]+(?:\s*,\s*(?:Deutschland|Germany|DE))?)\b", page_text)
        if loc_match:
            seller_location = loc_match.group(1).strip()
    keywords = [
        "Laserlicht", "Fari Laser", "Laser", "Head-up Display", "HUD",
        "Anhängerkupplung", "Gancio traino", "Panoramadach", "Tetto panoramico",
        "M Sport", "Harman Kardon", "Driving Assistant", "Parking Assistant",
        "xDrive", "RWD", "Sitzheizung", "Sedili riscaldabili", "Live Cockpit Professional"
    ]
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", page_text, re.IGNORECASE):
            if kw not in features:
                features.append(kw)

    clean_title = title.strip() if title else "Annuncio Auto mobile.de"

    # Build readable dense text representation for AI
    lines = [f"Titolo annuncio: {clean_title}"]
    if price_eur:
        lines.append(f"Prezzo: {price_eur} EUR")
    if mileage_km:
        lines.append(f"Chilometraggio: {mileage_km} km")
    if first_registration:
        lines.append(f"Anno/Prima immatricolazione: {first_registration}")
    if fuel_type:
        lines.append(f"Alimentazione/Motore: {fuel_type}")
    if power_kw_hp:
        lines.append(f"Potenza: {power_kw_hp}")
    if seller_location:
        lines.append(f"Luogo venditore: {seller_location}")
    if features:
        lines.append(f"Dotazioni/Optional rilevati: {', '.join(features)}")
    if description:
        lines.append(f"\nDescrizione venditore:\n{description.strip()}")

    raw_text = "\n".join(lines)

    return {
        "source_type": "mobile_de",
        "source_url": url or "",
        "title": clean_title,
        "raw_text": raw_text,
        "price_eur": price_eur,
        "mileage_km": mileage_km,
        "features": features,
        "images": images,
        "extraction": {
            "tier": "direct",
            "quality": "full",
            "http_status": 200,
        },
    }


async def extract_mobile_de(url: str, timeout: float = 12.0) -> Dict[str, Any]:
    """
    Downloads and extracts a listing from mobile.de handling WAF constraints.
    """
    logger.info(f"Extracting mobile.de listing from: {url}")
    response_status: Optional[int] = None
    try:
        async with httpx.AsyncClient(headers=MOBILE_DE_HEADERS, follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url)
            response_status = response.status_code
            if response.status_code == 200:
                res = parse_mobile_de_html(response.text, url=url)
                res["extraction"] = {
                    "tier": "direct",
                    "quality": "full",
                    "http_status": 200,
                }
                return res
            else:
                logger.warning(f"mobile.de responded with HTTP status {response.status_code}")
    except Exception as e:
        logger.warning(f"Error downloading mobile.de {url}: {e}")

    # Fallback assistito se Cloudflare blocca la richiesta diretta
    ad_id_match = re.search(r"id=(\d+)", url)
    ad_id = ad_id_match.group(1) if ad_id_match else "sconosciuto"
    fallback_text = (
        f"Annuncio mobile.de (ID: {ad_id})\n"
        f"URL: {url}"
    )
    return {
        "source_type": "mobile_de",
        "source_url": url,
        "title": f"Annuncio mobile.de (ID {ad_id})",
        "raw_text": fallback_text,
        "price_eur": None,
        "mileage_km": None,
        "features": [],
        "images": [],
        "extraction": {
            "tier": "fallback",
            "quality": "link_only",
            "http_status": response_status or 403,
        },
    }

