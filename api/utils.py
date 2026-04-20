import time
import random
from typing import Optional

# ─── UUID v7 ──────────────────────────────────────────────────────────────────

def generate_uuid7() -> str:
    ts_ms = int(time.time() * 1000)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    high = (ts_ms << 16) | (0x7 << 12) | rand_a
    low = (0b10 << 62) | rand_b
    hi = high.to_bytes(8, "big")
    lo = low.to_bytes(8, "big")
    return (
        f"{hi[0:4].hex()}-{hi[4:6].hex()}-{hi[6:8].hex()}"
        f"-{lo[0:2].hex()}-{lo[2:8].hex()}"
    )

# ─── Age classification ────────────────────────────────────────────────────────

def classify_age(age: int) -> str:
    if age <= 12:
        return "child"
    if age <= 19:
        return "teenager"
    if age <= 59:
        return "adult"
    return "senior"

# ─── Country data ─────────────────────────────────────────────────────────────

COUNTRY_NAMES: dict[str, str] = {
    "NG": "Nigeria", "KE": "Kenya", "GH": "Ghana", "ZA": "South Africa",
    "ET": "Ethiopia", "TZ": "Tanzania", "UG": "Uganda", "SN": "Senegal",
    "CI": "Ivory Coast", "CM": "Cameroon", "AO": "Angola", "BJ": "Benin",
    "RW": "Rwanda", "ZM": "Zambia", "MW": "Malawi", "MZ": "Mozambique",
    "ZW": "Zimbabwe", "SD": "Sudan", "EG": "Egypt", "MA": "Morocco",
    "DZ": "Algeria", "TN": "Tunisia", "LY": "Libya", "ML": "Mali",
    "NE": "Niger", "TD": "Chad", "SO": "Somalia", "ER": "Eritrea",
    "DJ": "Djibouti", "TG": "Togo", "GN": "Guinea", "SL": "Sierra Leone",
    "LR": "Liberia", "GA": "Gabon", "CG": "Congo", "CD": "DR Congo",
    "MG": "Madagascar", "NA": "Namibia", "BW": "Botswana", "LS": "Lesotho",
    "SZ": "Eswatini", "MU": "Mauritius", "CV": "Cape Verde", "GM": "Gambia",
    "BF": "Burkina Faso", "GW": "Guinea-Bissau", "ST": "São Tomé and Príncipe",
    "US": "United States", "CA": "Canada", "MX": "Mexico", "BR": "Brazil",
    "AR": "Argentina", "CO": "Colombia", "CL": "Chile", "PE": "Peru",
    "VE": "Venezuela", "GB": "United Kingdom", "FR": "France", "DE": "Germany",
    "IT": "Italy", "ES": "Spain", "PT": "Portugal", "NL": "Netherlands",
    "BE": "Belgium", "SE": "Sweden", "NO": "Norway", "DK": "Denmark",
    "FI": "Finland", "PL": "Poland", "RU": "Russia", "UA": "Ukraine",
    "RO": "Romania", "GR": "Greece", "TR": "Turkey", "IN": "India",
    "CN": "China", "JP": "Japan", "KR": "South Korea", "ID": "Indonesia",
    "PK": "Pakistan", "BD": "Bangladesh", "PH": "Philippines", "VN": "Vietnam",
    "TH": "Thailand", "MY": "Malaysia", "SG": "Singapore", "SA": "Saudi Arabia",
    "AE": "United Arab Emirates", "IR": "Iran", "IQ": "Iraq",
}

COUNTRY_LOOKUP: dict[str, str] = {
    # Africa
    "nigeria": "NG", "nigerian": "NG",
    "kenya": "KE", "kenyan": "KE",
    "ghana": "GH", "ghanaian": "GH",
    "south africa": "ZA", "south african": "ZA",
    "ethiopia": "ET", "ethiopian": "ET",
    "tanzania": "TZ", "tanzanian": "TZ",
    "uganda": "UG", "ugandan": "UG",
    "senegal": "SN", "senegalese": "SN",
    "ivory coast": "CI", "ivorian": "CI", "cote d'ivoire": "CI",
    "cameroon": "CM", "cameroonian": "CM",
    "angola": "AO", "angolan": "AO",
    "benin": "BJ", "beninese": "BJ",
    "rwanda": "RW", "rwandan": "RW",
    "zambia": "ZM", "zambian": "ZM",
    "malawi": "MW", "malawian": "MW",
    "mozambique": "MZ", "mozambican": "MZ",
    "zimbabwe": "ZW", "zimbabwean": "ZW",
    "sudan": "SD", "sudanese": "SD",
    "egypt": "EG", "egyptian": "EG",
    "morocco": "MA", "moroccan": "MA",
    "algeria": "DZ", "algerian": "DZ",
    "tunisia": "TN", "tunisian": "TN",
    "libya": "LY", "libyan": "LY",
    "mali": "ML", "malian": "ML",
    "niger": "NE", "nigerien": "NE",
    "chad": "TD", "chadian": "TD",
    "somalia": "SO", "somali": "SO",
    "eritrea": "ER", "eritrean": "ER",
    "djibouti": "DJ", "djiboutian": "DJ",
    "togo": "TG", "togolese": "TG",
    "guinea": "GN", "guinean": "GN",
    "sierra leone": "SL",
    "liberia": "LR", "liberian": "LR",
    "gabon": "GA", "gabonese": "GA",
    "congo": "CG", "congolese": "CG",
    "dr congo": "CD", "democratic republic of congo": "CD",
    "madagascar": "MG", "malagasy": "MG",
    "namibia": "NA", "namibian": "NA",
    "botswana": "BW",
    "lesotho": "LS",
    "eswatini": "SZ", "swaziland": "SZ",
    "mauritius": "MU", "mauritian": "MU",
    "cape verde": "CV",
    "gambia": "GM", "gambian": "GM",
    "burkina faso": "BF",
    # Americas
    "united states": "US", "usa": "US", "america": "US", "american": "US",
    "canada": "CA", "canadian": "CA",
    "brazil": "BR", "brazilian": "BR",
    "mexico": "MX", "mexican": "MX",
    "argentina": "AR", "argentinian": "AR",
    "colombia": "CO", "colombian": "CO",
    "chile": "CL", "chilean": "CL",
    "peru": "PE", "peruvian": "PE",
    "venezuela": "VE", "venezuelan": "VE",
    # Europe
    "united kingdom": "GB", "uk": "GB", "british": "GB", "england": "GB", "britain": "GB",
    "france": "FR", "french": "FR",
    "germany": "DE", "german": "DE",
    "italy": "IT", "italian": "IT",
    "spain": "ES", "spanish": "ES",
    "portugal": "PT", "portuguese": "PT",
    "netherlands": "NL", "dutch": "NL",
    "belgium": "BE", "belgian": "BE",
    "sweden": "SE", "swedish": "SE",
    "norway": "NO", "norwegian": "NO",
    "denmark": "DK", "danish": "DK",
    "finland": "FI", "finnish": "FI",
    "poland": "PL", "polish": "PL",
    "russia": "RU", "russian": "RU",
    "ukraine": "UA", "ukrainian": "UA",
    "romania": "RO", "romanian": "RO",
    "greece": "GR", "greek": "GR",
    "turkey": "TR", "turkish": "TR",
    # Asia
    "india": "IN", "indian": "IN",
    "china": "CN", "chinese": "CN",
    "japan": "JP", "japanese": "JP",
    "south korea": "KR", "korean": "KR",
    "indonesia": "ID", "indonesian": "ID",
    "pakistan": "PK", "pakistani": "PK",
    "bangladesh": "BD", "bangladeshi": "BD",
    "philippines": "PH", "filipino": "PH",
    "vietnam": "VN", "vietnamese": "VN",
    "thailand": "TH", "thai": "TH",
    "malaysia": "MY", "malaysian": "MY",
    "singapore": "SG", "singaporean": "SG",
    "saudi arabia": "SA", "saudi": "SA",
    "uae": "AE", "emirati": "AE", "united arab emirates": "AE",
    "iran": "IR", "iranian": "IR",
    "iraq": "IQ", "iraqi": "IQ",
}


def lookup_country_id(phrase: str) -> Optional[str]:
    phrase = phrase.lower().strip()
    if phrase in COUNTRY_LOOKUP:
        return COUNTRY_LOOKUP[phrase]
    words = phrase.split()
    for length in range(len(words), 0, -1):
        candidate = " ".join(words[:length])
        if candidate in COUNTRY_LOOKUP:
            return COUNTRY_LOOKUP[candidate]
    return None
