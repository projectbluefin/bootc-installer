"""Pure helpers for working with the finals list produced by wizard steps."""


def _extract_icon_and_name(finals):
    """Return ``(pretty_name, selected_icon)`` from a finals list.

    Scans *finals* (a list of dicts) and returns the first *pretty_name* and
    the first *icon* value found.  Returns ``(None, None)`` if neither is
    present.  Non-dict entries are skipped.
    """
    pretty_name = None
    selected_icon = None
    for f in finals:
        if isinstance(f, dict):
            if pretty_name is None and "pretty_name" in f:
                pretty_name = f["pretty_name"]
            if selected_icon is None and "icon" in f:
                selected_icon = f["icon"]
        if pretty_name and selected_icon:
            break
    return pretty_name, selected_icon
