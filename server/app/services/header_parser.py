import re
from datetime import datetime
from typing import Dict, Any, Optional

MIDA_RE = re.compile(r"\bCDE\d?/\d{4}/\d+\b", re.IGNORECASE)
PERIOD_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:hingga|to)\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

def _to_iso(ddmmyyyy: str) -> str:
    try:
        return datetime.strptime(ddmmyyyy, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ddmmyyyy

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

    return {
        "mida_no": mida_no,
        "company_name": company_name,
        "exemption_start": exemption_start,
        "exemption_end": exemption_end,
    }
