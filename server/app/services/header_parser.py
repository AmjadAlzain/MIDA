import re
from datetime import datetime
from typing import Dict, Any, Optional

MIDA_RE = re.compile(r"\bCDE\d?/\d{4}/\d+\b", re.IGNORECASE)
PERIOD_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:hingga|to)\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

# The two valid company names for MIDA certificates
VALID_COMPANY_NAMES = [
    "HONG LEONG YAMAHA MOTOR SDN BHD",
    "HICOM YAMAHA MOTOR SDN BHD",
]

def _to_iso(ddmmyyyy: str) -> str:
    try:
        return datetime.strptime(ddmmyyyy, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ddmmyyyy


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _fuzzy_match_company_name(ocr_name: Optional[str]) -> str:
    """
    Match OCR-extracted company name to one of the valid company names using fuzzy matching.
    Returns the closest matching valid company name.
    """
    if not ocr_name:
        # Default to Hong Leong if no name extracted
        return VALID_COMPANY_NAMES[0]
    
    ocr_upper = ocr_name.upper().strip()
    
    # Quick exact match check
    for valid_name in VALID_COMPANY_NAMES:
        if valid_name == ocr_upper:
            return valid_name
    
    # Check for substring match (company name might be part of a longer string)
    for valid_name in VALID_COMPANY_NAMES:
        if valid_name in ocr_upper or ocr_upper in valid_name:
            return valid_name
    
    # Check for key distinguishing words
    if "HONG LEONG" in ocr_upper or "HONGLEONG" in ocr_upper:
        return "HONG LEONG YAMAHA MOTOR SDN BHD"
    if "HICOM" in ocr_upper:
        return "HICOM YAMAHA MOTOR SDN BHD"
    
    # Fall back to Levenshtein distance
    min_distance = float('inf')
    best_match = VALID_COMPANY_NAMES[0]
    
    for valid_name in VALID_COMPANY_NAMES:
        distance = _levenshtein_distance(ocr_upper, valid_name)
        if distance < min_distance:
            min_distance = distance
            best_match = valid_name
    
    return best_match

def parse_header_fields(full_text: str) -> Dict[str, Optional[str]]:
    text = full_text or ""
    lines = text.splitlines()

    mida_no = None
    m = MIDA_RE.search(text)
    if m:
        mida_no = m.group(0).upper()

    exemption_start = exemption_end = None
    p = PERIOD_RE.search(text)
    if p:
        exemption_start = _to_iso(p.group(1))
        exemption_end = _to_iso(p.group(2))

    company_name = None
    
    # Strategy 1: Look for "Nama Syarikat" or "Company's Name"
    # and take the text following it or on the next line
    start_indices = []
    for i, line in enumerate(lines):
        if re.search(r"(Nama\s+Syarikat|Company'?s\s+Name)", line, re.IGNORECASE):
            start_indices.append(i)
            
    # Lines to skip when looking ahead for company name
    skip_patterns = [
        r"UNTUK KEGUNAAN RASMI",
        r"FOR OFFICIAL USE",
        r"Borang\s+TE\d+",
        r"Form\s+TE\d+",
        r"Nama\s+Syarikat",
        r"Company'?s\s+Name"
    ]
    skip_re = re.compile("|".join(skip_patterns), re.IGNORECASE)
    # Pattern to detect junk (only punctuation/whitespace)
    junk_re = re.compile(r"^[\s:.\-]*$")
    
    def is_valid_company_name(s: str) -> bool:
        """Check if string contains letters and is not a skip phrase."""
        if not s or junk_re.match(s):
            return False
        if not re.search(r"[A-Za-z]", s):
            return False
        if skip_re.search(s):
            return False
        return True
    
    for idx in start_indices:
        # Check if same line has content after ":"
        # e.g. "Nama Syarikat : ABC SDN BHD"
        line = lines[idx]
        # Find the LAST colon to handle "Nama Syarikat: Company's Name: ACTUAL COMPANY"
        colon_pos = line.rfind(":")
        if colon_pos != -1:
            cleaned = line[colon_pos + 1:].strip().lstrip(":-").strip()
        else:
            # No colon, remove the label itself
            cleaned = re.sub(r"(Nama\s+Syarikat|Company'?s\s+Name)", "", line, flags=re.IGNORECASE).strip()
            cleaned = cleaned.lstrip(":-").strip()
        
        if is_valid_company_name(cleaned) and len(cleaned) > 3:
            company_name = cleaned
            break
        
        # Look ahead next 3-5 non-empty lines for valid company name
        lookahead_count = 0
        for offset in range(1, 6):
            if idx + offset >= len(lines):
                break
            next_line = lines[idx + offset].strip().lstrip(":-").strip()
            if not next_line:
                continue  # Skip empty lines without counting
            lookahead_count += 1
            if lookahead_count > 5:
                break
            if is_valid_company_name(next_line):
                company_name = next_line
                break
        if company_name:
            break
    
    # Strategy 2: If strategy 1 failed or returned something suspicious (like just a label part), 
    # look for "SDN BHD"
    if not company_name or len(company_name) < 3:
        for line in lines:
            if "SDN BHD" in line.upper():
                company_name = line.strip()
                break

    # Apply fuzzy matching to normalize company name to one of the two valid options
    matched_company_name = _fuzzy_match_company_name(company_name)

    return {
        "mida_no": mida_no,
        "company_name": matched_company_name,
        "exemption_start": exemption_start,
        "exemption_end": exemption_end,
    }
