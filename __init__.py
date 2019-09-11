"""Turn into a proper python module."""

# Works around the fact that this is a module and can be approached
# as such. However, with EDMC's plugin loading, things
# can get a little messy and with this little hack, I try to keep my IDE happy.
from edsmquery import *  # pylint: disable=wildcard-import