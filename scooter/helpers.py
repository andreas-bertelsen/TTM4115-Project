def pretty_print(string: str, prefix: str):
    """
    Print a formatted string with a prefix.

    Args:
        string (str): The message to print.
        prefix (str): The prefix to display before the message.
    """
    print(f"{f'{prefix}:':<9} {string}")