from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsProcessingFeedback, QgsProject, QgsVectorLayer, QgsDataSourceUri
import psycopg2  # PostgreSQL adapter for Python
import processing
import os.path

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .school_locator_dialog import SchoolLocatorDialog


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

        self.dlg.show()

    def close_dialog(self):
        self.dlg.close()

    def run_analysis(self):
        """Runs the school suitability analysis using uploaded shapefiles."""
        feedback = QgsProcessingFeedback()

        try:
            # Retrieve uploaded file paths
            layer_paths = self.dlg.get_layer_paths()
            population_path = layer_paths.get("Population Data")
            school_path = layer_paths.get("School Layer")
            river_path = layer_paths.get("River Layer")
            boundary_path = layer_paths.get("Boundary Layer")

            # Validate that all files have been uploaded
            if not all([population_path, school_path, river_path, boundary_path]):
                QMessageBox.warning(self.dlg, "Input Error", "Please upload all required shapefiles.")
                return

            # Load layers
            population_layer = QgsVectorLayer(population_path, "Population Layer", "ogr")
            school_layer = QgsVectorLayer(school_path, "School Layer", "ogr")
            river_layer = QgsVectorLayer(river_path, "River Layer", "ogr")
            boundary_layer = QgsVectorLayer(boundary_path, "Boundary Layer", "ogr")

            if not all([population_layer.isValid(), school_layer.isValid(),
                        river_layer.isValid(), boundary_layer.isValid()]):
                QMessageBox.critical(self.dlg, "Layer Error", "One or more layers could not be loaded.")
                return

            # Add layers to QGIS project for visualization (optional)
            QgsProject.instance().addMapLayer(population_layer)
            QgsProject.instance().addMapLayer(school_layer)
            QgsProject.instance().addMapLayer(river_layer)
            QgsProject.instance().addMapLayer(boundary_layer)

            # Get user-defined parameters
            population_threshold = self.dlg.spin_population_threshold.value()
            school_distance = self.dlg.spin_distance_from_schools.value()
            river_distance = self.dlg.spin_river_distance_buffer.value()

            # Step 1: Clip population data to the boundary layer
            clipped_population = processing.run("native:clip", {
                'INPUT': population_layer,
                'OVERLAY': boundary_layer,
                'OUTPUT': 'memory:clipped_population'
            }, feedback=feedback)['OUTPUT']

            # Step 2: Filter high population areas
            high_population = processing.run("native:extractbyattribute", {
                'INPUT': clipped_population,
                'FIELD': 'population',  # Adjust field name as needed
                'OPERATOR': '>=',
                'VALUE': population_threshold,
                'OUTPUT': 'memory:high_population'
            }, feedback=feedback)['OUTPUT']

            # Step 3: Buffer existing schools
            school_buffer = processing.run("native:buffer", {
                'INPUT': school_layer,
                'DISTANCE': school_distance,
                'SEGMENTS': 5,
                'DISSOLVE': True,
                'OUTPUT': 'memory:school_buffer'
            }, feedback=feedback)['OUTPUT']

            # Step 4: Buffer rivers
            river_buffer = processing.run("native:buffer", {
                'INPUT': river_layer,
                'DISTANCE': river_distance,
                'SEGMENTS': 5,
                'DISSOLVE': True,
                'OUTPUT': 'memory:river_buffer'
            }, feedback=feedback)['OUTPUT']

            # Step 5: Combine buffers
            combined_buffer = processing.run("native:mergevectorlayers", {
                'LAYERS': [school_buffer, river_buffer],
                'OUTPUT': 'memory:combined_buffer'
            }, feedback=feedback)['OUTPUT']

            # Step 6: Identify suitable areas by removing buffered zones from high population
            suitable_areas = processing.run("native:difference", {
                'INPUT': high_population,
                'OVERLAY': combined_buffer,
                'OUTPUT': 'memory:suitable_areas'
            }, feedback=feedback)['OUTPUT']

            # Step 7: Clip suitable areas to boundary
            final_suitable_areas = processing.run("native:clip", {
                'INPUT': suitable_areas,
                'OVERLAY': boundary_layer,
                'OUTPUT': 'memory:final_suitable_areas'
            }, feedback=feedback)['OUTPUT']

            # Add the final suitable areas to QGIS
            suitable_layer = QgsVectorLayer(final_suitable_areas, "Suitable Areas", "memory")
            QgsProject.instance().addMapLayer(suitable_layer)

            QMessageBox.information(self.dlg, "Analysis Complete", "Suitable areas for schools have been identified.")

        except Exception as e:
            QMessageBox.critical(self.dlg, "Error", f"An error occurred: {str(e)}")
