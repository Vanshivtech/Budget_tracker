"""
Deterministic bank statement and CSV/UPI statement parser and categorizer.
Rules first, then past user categorizations, then cache, and batched LLM fallback.
Caps file size (2 MB) and row count (max 100 rows).
"""
import csv
import io
import re
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Tuple, Optional

from app.config import settings

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_ROWS = 100

# Canonical rule-based mapping for common merchants and keywords
RULE_MERCHANT_MAP: Dict[str, str] = {
    # Food & Dining
    "swiggy": "Food",
    "zomato": "Food",
    "blinkit": "Food",
    "zepto": "Food",
    "mcdonalds": "Food",
    "starbucks": "Food",
    "dominos": "Food",
    "kfc": "Food",
    "burger king": "Food",
    "pizza hut": "Food",
    "chaayos": "Food",
    "chai point": "Food",
    "subway": "Food",
    "haldiram": "Food",
    "bikanervala": "Food",
    "barbeque nation": "Food",
    "tea post": "Food",
    # Groceries
    "bigbasket": "Groceries",
    "dmart": "Groceries",
    "reliance fresh": "Groceries",
    "spencers": "Groceries",
    "natures basket": "Groceries",
    "supermarket": "Groceries",
    "kirana": "Groceries",
    "more retail": "Groceries",
    # Transport & Travel
    "uber": "Travel",
    "ola": "Travel",
    "rapido": "Travel",
    "irctc": "Travel",
    "makemytrip": "Travel",
    "redbus": "Travel",
    "goibibo": "Travel",
    "yatra": "Travel",
    "indigo": "Travel",
    "air india": "Travel",
    "cleartrip": "Travel",
    "petrol": "Travel",
    "fuel": "Travel",
    "indian oil": "Travel",
    "bharat petroleum": "Travel",
    "hpcl": "Travel",
    "shell": "Travel",
    "metro": "Travel",
    "fastag": "Travel",
    # Shopping
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "ajio": "Shopping",
    "meesho": "Shopping",
    "nykaa": "Shopping",
    "zara": "Shopping",
    "h&m": "Shopping",
    "decathlon": "Shopping",
    "tata cliq": "Shopping",
    "croma": "Shopping",
    "reliance digital": "Shopping",
    "ikea": "Shopping",
    "lifestyle": "Shopping",
    "westside": "Shopping",
    # Entertainment & Subscriptions
    "netflix": "Entertainment",
    "spotify": "Entertainment",
    "prime": "Entertainment",
    "hotstar": "Entertainment",
    "disney": "Entertainment",
    "bookmyshow": "Entertainment",
    "pvr": "Entertainment",
    "inox": "Entertainment",
    "youtube": "Entertainment",
    "sonyliv": "Entertainment",
    "zee5": "Entertainment",
    "audible": "Entertainment",
    # Health & Medical
    "apollo": "Health",
    "pharmeasy": "Health",
    "1mg": "Health",
    "netmeds": "Health",
    "medplus": "Health",
    "practo": "Health",
    "pharmacy": "Health",
    "chemist": "Health",
    "hospital": "Health",
    "diagnostic": "Health",
    "dr lal": "Health",
    # Bills & Utilities
    "bescom": "Bills",
    "tata power": "Bills",
    "adani electricity": "Bills",
    "electricity": "Bills",
    "water": "Bills",
    "gas": "Bills",
    "indane": "Bills",
    "hp gas": "Bills",
    "bharat gas": "Bills",
    "jio": "Bills",
    "airtel": "Bills",
    "vodafone": "Bills",
    "vi": "Bills",
    "bsnl": "Bills",
    "act fibernet": "Bills",
    "broadband": "Bills",
    "wifi": "Bills",
    "maintenance": "Bills",
    "society": "Bills",
    "rent": "Rent",
}


def parse_date_str(val: str) -> Optional[str]:
    """Parse various common bank statement date formats into YYYY-MM-DD."""
    if not val:
        return None
    val = val.strip()
    patterns = [
        ("%Y-%m-%d", r"^\d{4}-\d{2}-\d{2}$"),
        ("%d/%m/%Y", r"^\d{1,2}/\d{1,2}/\d{4}$"),
        ("%d-%m-%Y", r"^\d{1,2}-\d{1,2}-\d{4}$"),
        ("%d/%m/%y", r"^\d{1,2}/\d{1,2}/\d{2}$"),
        ("%d-%m-%y", r"^\d{1,2}-\d{1,2}-\d{2}$"),
        ("%d %b %Y", r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$"),
        ("%d-%b-%Y", r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"),
        ("%d-%b-%y", r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"),
        ("%b %d, %Y", r"^[A-Za-z]{3}\s+\d{1,2},\s*\d{4}$"),
        ("%Y/%m/%d", r"^\d{4}/\d{2}/\d{2}$"),
    ]
    for fmt, regex in patterns:
        if re.match(regex, val, re.IGNORECASE):
            try:
                dt = datetime.strptime(val, fmt)
                # Handle 2-digit years reasonably
                if dt.year < 2000:
                    dt = dt.replace(year=dt.year + 100)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    # Fallback to dateutil if available
    try:
        from dateutil import parser as dparser
        dt = dparser.parse(val, fuzzy=True, dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return date.today().isoformat()


def clean_amount(val: Any) -> float:
    """Extract float amount, removing currency symbols, commas, spaces."""
    if val is None:
        return 0.0
    s = str(val).strip().replace(",", "").replace("\u20b9", "").replace("Rs", "").replace("INR", "").strip()
    if not s or s == "-":
        return 0.0
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def auto_detect_columns(headers: List[str]) -> Dict[str, Optional[int]]:
    """Detect column indexes for date, description, debit, credit, balance from header list."""
    mapping: Dict[str, Optional[int]] = {
        "date": None,
        "description": None,
        "debit": None,
        "credit": None,
        "amount": None,
        "balance": None,
    }

    norm_headers = [h.lower().strip().replace("_", " ").replace(".", "") for h in headers]

    for idx, h in enumerate(norm_headers):
        # Date column
        if mapping["date"] is None and any(k in h for k in ["date", "txn dt", "value dt", "trans date"]):
            mapping["date"] = idx
            continue

        # Description column
        if mapping["description"] is None and any(k in h for k in ["narration", "description", "particulars", "remarks", "details", "merchant", "note"]):
            mapping["description"] = idx
            continue

        # Debit column
        if mapping["debit"] is None and any(k == h or k in h for k in ["debit", "withdrawal", "dr", "dr amount", "debit amount", "withdrawals"]):
            mapping["debit"] = idx
            continue

        # Credit column
        if mapping["credit"] is None and any(k == h or k in h for k in ["credit", "deposit", "cr", "cr amount", "credit amount", "deposits"]):
            mapping["credit"] = idx
            continue

        # Single amount column
        if mapping["amount"] is None and h in ["amount", "txn amount", "transaction amount", "total"]:
            mapping["amount"] = idx
            continue

        # Balance column
        if mapping["balance"] is None and any(k in h for k in ["balance", "bal", "closing bal"]):
            mapping["balance"] = idx
            continue

    return mapping


def parse_csv_content(
    content_text: str,
    manual_mapping: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Parse CSV text into normalized row dicts."""
    lines = [line for line in content_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("CSV content is empty.")

    # Find the header row (sometimes banks add title rows at top)
    header_idx = 0
    reader_rows = []
    # Try sniffer or standard csv reader
    try:
        sample = "\n".join(lines[:10])
        dialect = csv.Sniffer().sniff(sample)
        reader = list(csv.reader(lines, dialect))
    except Exception:
        reader = list(csv.reader(lines))

    if not reader:
        raise ValueError("Could not parse CSV format.")

    # Look for a row containing 'date' or 'amount' or 'narration' or 'description'
    for i, r in enumerate(reader[:15]):
        lower_cells = " ".join(str(c).lower() for c in r)
        if ("date" in lower_cells and ("amount" in lower_cells or "debit" in lower_cells or "narration" in lower_cells or "description" in lower_cells)):
            header_idx = i
            break

    headers = reader[header_idx]
    col_map = auto_detect_columns(headers)

    # Apply manual mapping fallback if provided
    if manual_mapping:
        for target, col_name in manual_mapping.items():
            if col_name in headers:
                col_map[target] = headers.index(col_name)

    # Validate that we have at least date and either (debit/credit) or (amount)
    if col_map["date"] is None:
        col_map["date"] = 0  # Fallback to first column

    if col_map["description"] is None:
        # Fallback to column 1 if available
        col_map["description"] = 1 if len(headers) > 1 else 0

    parsed_rows: List[Dict[str, Any]] = []

    for row_idx, row in enumerate(reader[header_idx + 1:]):
        if not row or all(not str(c).strip() for c in row):
            continue
        if len(parsed_rows) >= MAX_ROWS:
            break

        # Extract date
        raw_date = row[col_map["date"]] if col_map["date"] < len(row) else ""
        date_str = parse_date_str(raw_date)

        # Extract description
        raw_desc = row[col_map["description"]] if col_map["description"] < len(row) else ""
        raw_desc = str(raw_desc).strip()
        if not raw_desc and not raw_date:
            continue

        # Extract debit / credit
        debit_amt = 0.0
        credit_amt = 0.0

        if col_map["debit"] is not None and col_map["debit"] < len(row):
            debit_amt = clean_amount(row[col_map["debit"]])

        if col_map["credit"] is not None and col_map["credit"] < len(row):
            credit_amt = clean_amount(row[col_map["credit"]])

        if debit_amt == 0.0 and credit_amt == 0.0 and col_map["amount"] is not None and col_map["amount"] < len(row):
            amt = clean_amount(row[col_map["amount"]])
            # Check for Dr/Cr text in row or minus sign
            row_str = " ".join(str(c).lower() for c in row)
            if "cr" in row_str or "credit" in row_str or "deposit" in row_str:
                credit_amt = amt
            else:
                debit_amt = amt

        if debit_amt == 0.0 and credit_amt == 0.0:
            continue

        is_credit = credit_amt > 0.0 and debit_amt == 0.0
        final_amt = credit_amt if is_credit else debit_amt

        parsed_rows.append({
            "raw_date": raw_date,
            "date": date_str,
            "description": raw_desc,
            "amount": final_amt,
            "is_credit": is_credit,
        })

    return parsed_rows


def parse_plain_text_statements(text: str) -> List[Dict[str, Any]]:
    """Parse pasted bank SMS / UPI text lines deterministically with regex."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    parsed_rows: List[Dict[str, Any]] = []

    # Patterns for SMS / UPI notification formats:
    # 1. "Paid Rs. 350 to Swiggy on 12-10-2026"
    # 2. "A/c debited by INR 1,200.00 on 14/10/26 for Uber"
    # 3. "Spent Rs 450 at DMart on 15 Oct"
    # 4. "Credited INR 50,000 from Salary on 01-10-2026"
    amt_regex = re.compile(r"(?:rs\.?|inr)\s*([0-9,]+(?:\.[0-9]{1,2})?)", re.IGNORECASE)
    date_regex = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}(?:\s+\d{2,4})?)", re.IGNORECASE)

    for line in lines:
        if len(parsed_rows) >= MAX_ROWS:
            break

        amt_match = amt_regex.search(line)
        if not amt_match:
            # Check if line has just numbers separated by tabs/commas/spaces
            parts = [p.strip() for p in re.split(r"[\t,;]", line) if p.strip()]
            if len(parts) >= 3:
                # Attempt to parse as date, desc, amount
                d = parse_date_str(parts[0])
                amt = clean_amount(parts[-1])
                if amt > 0:
                    desc = " ".join(parts[1:-1])
                    is_cr = any(k in line.lower() for k in ["credit", "cr", "received", "deposit"])
                    parsed_rows.append({
                        "raw_date": parts[0],
                        "date": d,
                        "description": desc,
                        "amount": amt,
                        "is_credit": is_cr,
                    })
            continue

        amt = clean_amount(amt_match.group(1))
        d_match = date_regex.search(line)
        d_str = parse_date_str(d_match.group(1)) if d_match else date.today().isoformat()

        is_credit = any(w in line.lower() for w in ["credited", "received", "credit", "refund", "cashback"])

        # Clean description by stripping out the amount and date
        desc = line
        desc = amt_regex.sub("", desc)
        if d_match:
            desc = desc.replace(d_match.group(1), "")
        desc = re.sub(r"\b(paid to|debited for|spent at|credited from|transfer to|a/c|avl bal|ref no|upi ref|txn id)\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\s+", " ", desc).strip(" :-,.")

        if not desc:
            desc = "UPI Payment"

        parsed_rows.append({
            "raw_date": d_match.group(1) if d_match else "",
            "date": d_str,
            "description": desc,
            "amount": amt,
            "is_credit": is_credit,
        })

    return parsed_rows


def categorize_by_rule(normalized_merchant: str, raw_desc: str) -> Optional[str]:
    """Check rule dictionary for category match."""
    key = normalized_merchant.lower().strip()
    if key in RULE_MERCHANT_MAP:
        return RULE_MERCHANT_MAP[key]

    raw_lower = raw_desc.lower()
    for merchant_key, cat in RULE_MERCHANT_MAP.items():
        if merchant_key in raw_lower or merchant_key in key:
            return cat
    return None


def batch_llm_categorize(
    uncategorized_items: List[Dict[str, str]],
    allowed_categories: List[str],
) -> Dict[str, str]:
    """Batch-categorize unknown merchants into ONE single LLM call.
    uncategorized_items: list of {"merchant": "...", "description": "..."}
    Returns: {merchant_key: category}
    """
    if not uncategorized_items:
        return {}

    from app.llm import execute_with_fallback
    from langchain_core.messages import SystemMessage, HumanMessage

    cats_str = ", ".join(allowed_categories)
    items_to_send = []
    seen = set()
    for item in uncategorized_items:
        m = item["merchant"]
        if m not in seen:
            seen.add(m)
            items_to_send.append({"merchant": m, "sample_text": item["description"][:60]})

    prompt = (
        f"You are a strict financial categorizer. Classify each of the following merchants into exactly ONE category from this list: [{cats_str}].\n"
        f"If none fits well, choose 'Other'.\n"
        f"Return ONLY a valid JSON object mapping merchant name to category. Example: {{\"Swiggy\": \"Food\", \"Decathlon\": \"Shopping\"}}.\n"
        f"Do not include any explanation, markdown formatting, or emojis.\n\n"
        f"Merchants to classify:\n{json.dumps(items_to_send)}"
    )

    messages = [
        SystemMessage(content="You are a deterministic financial categorizer. Output only JSON."),
        HumanMessage(content=prompt),
    ]

    try:
        response_text = execute_with_fallback(messages)
        # Clean json
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        result_dict = json.loads(clean_text)
        return {k: str(v) for k, v in result_dict.items() if str(v) in allowed_categories or str(v) == "Other"}
    except Exception as e:
        logger.error(f"Error in batch LLM categorization: {e}")
        return {}
