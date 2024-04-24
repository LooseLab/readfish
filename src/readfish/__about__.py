"""__about__.py
Version of the read until software
"""

__version__ = "2024.0.0"
# Warning is the last supported version of MinKNOW for this version of readfish
# Users running this version will receive the warning shown if they are running this version of readfish.
__warning__ = [["5.9", f"Readfish {__version__} will not be supported in the next version of MinKNOW. Please update to the latest version of Readfish or do not update MinKNOW if you are concerned about version control."]]
# Compatability is either the maximum or minimum version of MinKNOW that this version of readfish is compatible with.
__compatability__ = [["6.0","lte"]]
