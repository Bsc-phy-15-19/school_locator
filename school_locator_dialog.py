import os
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from PyQt5.QtWidgets import QFileDialog




# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'school_locator_dialog_base.ui'))


class SchoolLocatorDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(SchoolLocatorDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS
        self.setupUi(self)

        # Set the size of the window programmatically
        self.setFixedSize(500, 600)  # Fixed window size

        # Set the size of the 'Close' and 'Run Analysis' buttons
        self.btn_close.setFixedSize(100, 30)  # Set fixed size for Close button
        self.btn_run_analysis.setFixedSize(100, 30)  # Set fixed size for Run Analysis button

        # To ensure the buttons don't resize with the dialog, set their size policies
        self.btn_close.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.btn_run_analysis.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        # Connect upload buttons to their file selection actions
        self.btn_population_layer.clicked.connect(lambda: self.upload_layer("Population Data"))
        self.btn_school_layer.clicked.connect(lambda: self.upload_layer("School Layer"))
        self.btn_river_layer.clicked.connect(lambda: self.upload_layer("River Layer"))
        self.btn_boundary_layer.clicked.connect(lambda: self.upload_layer("Boundary Layer"))

        # Storage for file paths
        self.layer_paths = {
            "Population Data": None,
            "School Layer": None,
            "River Layer": None,
            "Boundary Layer": None
        }

    def upload_layer(self, layer_name):
        """Handles file upload for the specified layer."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            f"Select Shapefile for {layer_name}", 
            "", 
            "Shapefiles (*.shp)"
        )

        if file_path:
            # Store the file path in the dictionary
            self.layer_paths[layer_name] = file_path
            QtWidgets.QMessageBox.information(self, "File Selected", f"{layer_name} loaded successfully.")
        else:
            QtWidgets.QMessageBox.warning(self, "File Not Selected", f"No file selected for {layer_name}.")

    def get_layer_paths(self):
        """Returns the file paths for all uploaded layers."""
        return self.layer_paths
