"""EDSMQuery Plugin."""

from version import VERSION, NAME as PLUGIN_NAME


def plugin_start():
    """Perform plugin initialization."""

    print("Loaded {name} (v{version}).".format(name=PLUGIN_NAME, version=VERSION))
    return PLUGIN_NAME
