"""
shipping.py  –  Transport cost estimator
Smješta se u logic/shipping.py

Upotreba u containers.py:
    from logic.shipping import estimate_shipping
    costs = estimate_shipping(cbm=18, goods_value_aud=50000, route="canada_perth")
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Konfiguracione konstante (ažuriraj po potrebi)
# ---------------------------------------------------------------------------

# Ocean freight baze (USD) – okvirne tržišne vrednosti Q1 2025
OCEAN_RATES_USD = {
    "20ft": {"min": 2500, "mid": 3200, "max": 4000},
    "40ft": {"min": 4000, "mid": 5500, "max": 7000},
}

# LCL rate po CBM (USD)
LCL_RATE_PER_CBM_USD = {"min": 150, "mid": 200, "max": 280}

# Fiksni dodatni troškovi (AUD)
FIXED_EXTRAS_AUD = {
    "origin_thc":         450,   # Terminal Handling Charge – polazna luka
    "destination_thc":    550,   # Terminal Handling Charge – Fremantle
    "customs_broker":     450,   # Carinski agent AU
    "baf_surcharge":      550,   # Gorivo/BAF surcharge
    "inland_trucking":    800,   # Kamion do/od luke
}

# Australijske dažbine
DUTY_RATE    = 0.05   # 5% carina (opšta stopa, Kanada nema FTA sa AU)
GST_RATE     = 0.10   # 10% GST na (CIF + carina)

# Preporučena granica FCL vs LCL (CBM)
LCL_FCL_BREAKEVEN_CBM = 20

# ---------------------------------------------------------------------------
# Dataclass za rezultat
# ---------------------------------------------------------------------------

@dataclass
class ShippingCost:
    container_type: str        # '20ft_fcl', '40ft_fcl', 'lcl'
    cbm: float
    fill_pct: float            # 0.0–1.0

    ocean_freight_aud: float
    fixed_extras_aud: float
    insurance_aud: float
    duty_aud: float
    gst_aud: float

    total_aud: float
    note: str = ""

    def per_cbm(self) -> float:
        return round(self.total_aud / self.cbm, 2) if self.cbm else 0

    def summary(self) -> dict:
        return {
            "container":        self.container_type,
            "cbm":              self.cbm,
            "fill_%":           round(self.fill_pct * 100, 1),
            "ocean_AUD":        round(self.ocean_freight_aud, 2),
            "extras_AUD":       round(self.fixed_extras_aud, 2),
            "insurance_AUD":    round(self.insurance_aud, 2),
            "duty_AUD":         round(self.duty_aud, 2),
            "gst_AUD":          round(self.gst_aud, 2),
            "TOTAL_AUD":        round(self.total_aud, 2),
            "per_cbm_AUD":      self.per_cbm(),
            "note":             self.note,
        }


# ---------------------------------------------------------------------------
# Pomoćne funkcije
# ---------------------------------------------------------------------------

def _usd_to_aud(usd: float, rate: float) -> float:
    return usd * rate


def _ocean_fcl(container: str, scenario: str, rate: float) -> float:
    """Vraća ocean freight u AUD za FCL."""
    usd = OCEAN_RATES_USD[container][scenario]
    return _usd_to_aud(usd, rate)


def _ocean_lcl(cbm: float, scenario: str, rate: float) -> float:
    """Vraća ocean freight u AUD za LCL."""
    usd_per_cbm = LCL_RATE_PER_CBM_USD[scenario]
    return _usd_to_aud(usd_per_cbm * cbm, rate)


def _duty_and_gst(goods_value_aud: float, freight_aud: float, insurance_aud: float) -> tuple:
    """
    Vraća (duty, gst) u AUD.
    CIF osnova = goods_value + freight + insurance
    duty = CIF × 5%
    gst  = (CIF + duty) × 10%
    """
    cif = goods_value_aud + freight_aud + insurance_aud
    duty = cif * DUTY_RATE
    gst  = (cif + duty) * GST_RATE
    return round(duty, 2), round(gst, 2)


# ---------------------------------------------------------------------------
# Glavni API
# ---------------------------------------------------------------------------

CONTAINER_CBM = {"20ft": 25.0, "40ft": 55.0}


def estimate_shipping(
    cbm: float,
    goods_value_aud: float,
    usd_aud_rate: float = 1.58,
    scenario: str = "mid",          # 'min' | 'mid' | 'max'
    force_container: str = None,    # '20ft' | '40ft' | 'lcl' | None (auto)
    insurance_pct: float = 0.015,   # 1.5% CIF
) -> ShippingCost:
    """
    Parametri:
        cbm              – kubni metri robe
        goods_value_aud  – vrednost robe u AUD (FOB)
        usd_aud_rate     – trenutni USD/AUD kurs (default 1.58)
        scenario         – 'min', 'mid', 'max' (konzervativno/srednje/worst-case)
        force_container  – ako None, auto-bira optimalno
        insurance_pct    – procenat osiguranja od CIF vrednosti

    Vraća: ShippingCost dataclass
    """

    if scenario not in ("min", "mid", "max"):
        raise ValueError("scenario mora biti 'min', 'mid' ili 'max'")

    # --- Auto-odabir kontejnera ---
    if force_container is None:
        if cbm <= LCL_FCL_BREAKEVEN_CBM:
            container_type = "lcl"
        elif cbm <= CONTAINER_CBM["20ft"]:
            container_type = "20ft"
        else:
            container_type = "40ft"
    else:
        container_type = force_container

    # --- Ocean freight ---
    if container_type == "lcl":
        ocean_aud = _ocean_lcl(cbm, scenario, usd_aud_rate)
        fill_pct  = cbm / CONTAINER_CBM["20ft"]   # referentno
        label     = "lcl"
    else:
        size = container_type  # '20ft' ili '40ft'
        ocean_aud = _ocean_fcl(size, scenario, usd_aud_rate)
        fill_pct  = cbm / CONTAINER_CBM[size]
        label     = f"{size}_fcl"

    # --- Fiksni dodaci ---
    extras_aud = sum(FIXED_EXTRAS_AUD.values())

    # --- Osiguranje (1.5% od goods + ocean) ---
    insurance_aud = (goods_value_aud + ocean_aud) * insurance_pct

    # --- Carina i GST ---
    duty_aud, gst_aud = _duty_and_gst(goods_value_aud, ocean_aud, insurance_aud)

    # --- Ukupno ---
    total = ocean_aud + extras_aud + insurance_aud + duty_aud + gst_aud

    # --- Napomena ako je loše popunjen FCL ---
    note = ""
    if container_type != "lcl" and fill_pct < 0.5:
        note = f"⚠️  Kontejner samo {fill_pct*100:.0f}% pun – razmotri LCL ili konsolidaciju"

    return ShippingCost(
        container_type=label,
        cbm=cbm,
        fill_pct=fill_pct,
        ocean_freight_aud=round(ocean_aud, 2),
        fixed_extras_aud=round(extras_aud, 2),
        insurance_aud=round(insurance_aud, 2),
        duty_aud=duty_aud,
        gst_aud=gst_aud,
        total_aud=round(total, 2),
        note=note,
    )


def compare_options(cbm: float, goods_value_aud: float, usd_aud_rate: float = 1.58) -> list[dict]:
    """
    Vraća sve opcije uporedo (LCL, 20ft, 40ft) za datu količinu.
    Korisno za prikaz u UI ili report.
    """
    results = []
    for option in ("lcl", "20ft", "40ft"):
        try:
            r = estimate_shipping(
                cbm=cbm,
                goods_value_aud=goods_value_aud,
                usd_aud_rate=usd_aud_rate,
                force_container=option,
            )
            results.append(r.summary())
        except Exception as e:
            results.append({"container": option, "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Brzi test (python logic/shipping.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=== Auto-odabir (12 CBM) ===")
    r = estimate_shipping(cbm=12, goods_value_aud=30000)
    print(json.dumps(r.summary(), indent=2))

    print("\n=== Auto-odabir (22 CBM) ===")
    r = estimate_shipping(cbm=22, goods_value_aud=60000)
    print(json.dumps(r.summary(), indent=2))

    print("\n=== Poređenje svih opcija (18 CBM, $50k robe) ===")
    for row in compare_options(cbm=18, goods_value_aud=50000):
        print(json.dumps(row, indent=2))
