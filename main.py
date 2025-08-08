# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.


from PyQt5.QtWidgets import QApplication
import sys
from gui.ui_main import ReconCraftUI

def main():
    app = QApplication(sys.argv)
    window = ReconCraftUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
