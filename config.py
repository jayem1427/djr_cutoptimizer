# Application globals shared across the add-in (same layout as djr_batchpost).
import os

# More logging in the Text Command window. False for releases.
DEBUG = False

# Fusion loads <folder>/<folder>.py, so IDs follow the folder name.
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = 'DJR'

PLUGIN_VERSION = '0.1.1'
