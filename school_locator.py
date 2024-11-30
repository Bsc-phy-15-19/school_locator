from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QFileDialog
from qgis.core import QgsProcessingFeedback, QgsProject, QgsVectorLayer, QgsDataSourceUri
import processing

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .school_locator_dialog import SchoolLocatorDialog
import os.path


class SchoolLocator:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        # Set up localization
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir, 'i18n', f'SchoolLocator_{locale}.qm'
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Instance attributes
        self.actions = []
        self.menu = self.tr(u'&school_locator')
        self.dlg = None

    def tr(self, message):
        """Translate a string using Qt translation API."""
        return QCoreApplication.translate('SchoolLocator', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip:
            action.setStatusTip(status_tip)

        if whats_this:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = ':/plugins/school_locator/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Locator'),
            callback=self.run,
            parent=self.iface.mainWindow(),
        )

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        if not self.dlg:
            self.dlg = SchoolLocatorDialog()

            # Connect dialog buttons to their respective methods
            self.dlg.btn_close.clicked.connect(self.close_dialog)
            self.dlg.btn_run_analysis.clicked.connect(self.run_analysis)

            # Add file selection for each input
            self.dlg.combo_population_layer.currentIndexChanged.connect(
                lambda: self.import_to_database('population'))
            self.dlg.combo_school_layer.currentIndexChanged.connect(
                lambda: self.import_to_database('school'))
            self.dlg.combo_land_use_layer.currentIndexChanged.connect(
                lambda: self.import_to_database('land_use'))
            self.dlg.combo_area_layer.currentIndexChanged.connect(
                lambda: self.import_to_database('area'))

        self.dlg.show()

    def close_dialog(self):
        self.dlg.close()

    def import_to_database(self, layer_type):
        """Handles importing shapefiles to the database."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.dlg,
            "Select Shapefile",
            "",
            "Shapefiles (*.shp)"
        )

        if not file_path:
            return

        # Import to database (PostGIS example)
        feedback = QgsProcessingFeedback()
        table_name = f"{layer_type}_layer"

        try:
            processing.run("qgis:importintopostgis", {
                'INPUT': file_path,
                'DATABASE': 'locator',  # Connection name from QGIS DB Manager
                'SCHEMA': 'public',
                'TABLE': locator,
                'OVERWRITE': True,
                'PRIMARY_KEY': 'id',
                'LOWERCASE_NAMES': True,
                'DROP_STRING_LENGTH': False,
                'CODING': 'UTF-8'
            }, feedback=feedback)

            QMessageBox.information(self.dlg, "Import Successful", f"{layer_type.capitalize()} layer imported successfully.")
        except Exception as e:
            QMessageBox.critical(self.dlg, "Import Error", f"Failed to import {layer_type} layer: {str(e)}")

    def run_analysis(self):
        """Executes spatial analysis logic on database layers."""
        # Fetch user inputs
        population_layer_name = 'population_layer'
        school_layer_name = 'school_layer'
        land_use_layer_name = 'land_use_layer'
        area_layer_name = 'area_layer'
        population_threshold = self.dlg.spin_population_threshold.value()
        max_distance = self.dlg.spin_distance_from_schools.value()
        buffer_distance = self.dlg.spin_restricted_zone_buffer.value()

        # Validate inputs
        if not all([population_layer_name, school_layer_name, land_use_layer_name, area_layer_name]):
            QMessageBox.warning(self.dlg, "Input Error", "Please ensure all layers have been imported to the database.")
            return

        feedback = QgsProcessingFeedback()

        try:
            # Step 1: Clip population and land use layers by the area boundary
            clipped_population = processing.run("native:clip", {
                'INPUT': f"public.{population_layer_name}",
                'OVERLAY': f"public.{area_layer_name}",
                'OUTPUT': 'memory:'
            }, feedback=feedback)['OUTPUT']

            clipped_land_use = processing.run("native:clip", {
                'INPUT': f"public.{land_use_layer_name}",
                'OVERLAY': f"public.{area_layer_name}",
                'OUTPUT': 'memory:'
            }, feedback=feedback)['OUTPUT']

            # Step 2: Buffer existing schools
            school_buffer = processing.run("native:buffer", {
                'INPUT': f"public.{school_layer_name}",
                'DISTANCE': buffer_distance,
                'SEGMENTS': 5,
                'DISSOLVE': True,
                'OUTPUT': 'memory:'
            }, feedback=feedback)['OUTPUT']

            # Step 3: Remove buffered areas (unsuitable zones)
            available_land = processing.run("native:difference", {
                'INPUT': clipped_land_use,
                'OVERLAY': school_buffer,
                'OUTPUT': 'memory:'
            }, feedback=feedback)['OUTPUT']

            # Step 4: Filter population areas by threshold
            suitable_population = processing.run("native:extractbyattribute", {
                'INPUT': clipped_population,
                'FIELD': 'population',
                'OPERATOR': '>=',
                'VALUE': population_threshold,
                'OUTPUT': 'memory:'
            }, feedback=feedback)['OUTPUT']

            # Step 5: Intersect suitable population areas with available land
            suitable_locations = processing.run("native:intersection", {
                'INPUT': suitable_population,
                'OVERLAY': available_land,
                'OUTPUT': 'memory:'
            }, feedback=feedback)['OUTPUT']

            # Add the result to the QGIS project
            QgsProject.instance().addMapLayer(suitable_locations)

            self.dlg.lbl_status_message.setText("Status: Analysis complete.")
            QMessageBox.information(self.dlg, "Analysis Complete", "Suitable locations have been identified.")

        except Exception as e:
            self.dlg.lbl_status_message.setText("Status: Analysis failed.")
            QMessageBox.critical(self.dlg, "Analysis Error", f"An error occurred during the analysis: {str(e)}")
