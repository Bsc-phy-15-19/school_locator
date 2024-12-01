import os
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'school_locator_dialog_base.ui'))


class SchoolLocatorDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(SchoolLocatorDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots.
        self.setupUi(self)

        # Set the size of the window programmatically
        self.setFixedSize(500, 600)  # Fixed window size

        # Set the size of the 'Close' and 'Run Analysis' buttons
        self.btn_close.setFixedSize(100, 30)  # Set fixed size for Close button
        self.btn_run_analysis.setFixedSize(100, 30)  # Set fixed size for Run Analysis button

        # To ensure the buttons don't resize with the dialog, set their size policies
        self.btn_close.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.btn_run_analysis.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
