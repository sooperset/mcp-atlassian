from datetime import datetime

from dateutil.parser import isoparse


def parse_iso8601_date(date_string: str) -> datetime | None:
    """
    Validates of string is in ISO 8601 date format YYYY-MM-DDThh:mm:ss.sssZ

    Args:
        date_string (str): The string to validate.

    Returns:
        bool: date if the string is a valid ISO 8601 date/time, otherwise raises ValueError.
    """
    try:
        return isoparse(date_string)
    except ValueError as err:
        raise ValueError(
            "Incorrect data format, should be YYYY-MM-DDThh:mm:ss.sssZ"
        ) from err
