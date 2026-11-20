from ...config import ADDIN_NAME, COMPANY_NAME

CMD_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_optimizeFeeds'
CMD_NAME = 'Optimize feeds & speeds'
CMD_DESCRIPTION = ('Open the cut optimizer for the selected operation: reads the tool and cutting data, '
                   'and picks spindle speed, feed, stepover and stepdown for the highest removal rate inside your limits.')

PALETTE_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_palette'
PALETTE_NAME = 'DJR Cut Optimizer'
PALETTE_WIDTH = 460
PALETTE_HEIGHT = 900

CAM_WORKSPACE_ID = 'CAMEnvironment'
CAM_ACTIONS_PANEL_ID = 'CAMActionPanel'
CAM_PRODUCT_ID = 'CAMProductType'

# Material is asked once per setup and kept on the setup.
ATTR_GROUP = 'djr_cutcalc'
ATTR_MATERIAL = 'material'
