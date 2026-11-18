def require_business_id(value: object, label: str = "business id") -> int:
    """Business numbers are positive integers returned by the ledger; bools are not."""
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value
