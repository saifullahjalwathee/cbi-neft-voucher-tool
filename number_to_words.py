"""
number_to_words.py
Converts a rupee amount into words using the Indian numbering system
(Thousand / Lakh / Crore), the way Indian bank forms expect it.

Example:
    amount_to_words(2500000) -> "Rupees Twenty Five Lakh Only"
    amount_to_words(1234.50) -> "Rupees One Thousand Two Hundred Thirty Four and Fifty Paise Only"
"""

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]


def _two_digits(n):
    if n < 20:
        return ONES[n]
    return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()


def _three_digits(n):
    if n >= 100:
        rest = n % 100
        return (ONES[n // 100] + " Hundred" + (" " + _two_digits(rest) if rest else "")).strip()
    return _two_digits(n)


def _int_to_words_indian(n):
    """Convert a non-negative integer to words using lakh/crore grouping."""
    if n == 0:
        return "Zero"

    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1000)
    hundred = n

    parts = []
    if crore:
        parts.append(_three_digits(crore) + " Crore")
    if lakh:
        parts.append(_three_digits(lakh) + " Lakh")
    if thousand:
        parts.append(_three_digits(thousand) + " Thousand")
    if hundred:
        parts.append(_three_digits(hundred))

    return " ".join(parts)


def amount_to_words(amount, prefix="Rupees", suffix="Only"):
    """
    amount: number or numeric string, e.g. 2500000 or "2500000.50"
    Returns a string like "Rupees Twenty Five Lakh Only".
    """
    amount = round(float(amount), 2)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))

    words = _int_to_words_indian(rupees)

    if paise:
        words += " and " + _two_digits(paise) + " Paise"

    result = f"{prefix} {words} {suffix}".strip()
    # collapse any accidental double spaces
    return " ".join(result.split())
