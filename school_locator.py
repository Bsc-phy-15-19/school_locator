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

        # Database connection parameters
        self.db_params = {
            'database': 'locator',
            'user': 'postgres',
            'password': 'wedson123',
            'host': 'localhost',
            'port': '5432'
        }

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
        """Display the plugin dialog and populate input layers."""
        if not self.dlg:
            self.dlg = SchoolLocatorDialog()

            # Connect dialog buttons to their respective methods
            self.dlg.btn_close.clicked.connect(self.close_dialog)
            self.dlg.btn_run_analysis.clicked.connect(self.run_analysis)

            # Populate the combo boxes with available layers in QGIS
            self.populate_input_layers()

        self.dlg.show()

    def close_dialog(self):
        self.dlg.close()

    def connect_to_postgis(self):
        """Connect to the PostGIS database."""
        try:
            conn = psycopg2.connect(**self.db_params)
            return conn
        except Exception as e:
            QMessageBox.critical(self.dlg, "Database Connection Error", str(e))
            return None

    def get_districts(self):
        """Retrieve a list of districts from the database."""
        conn = self.connect_to_postgis()
        
        if conn is None:
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name FROM districts;")
                districts = cursor.fetchall()
                return districts
        except Exception as e:
            QMessageBox.critical(self.dlg, "Error Fetching Districts", str(e))
            return []
        finally:
            conn.close()

    def load_layer_from_postgis(self, uri, schema, table, geometry_column):
        """Loads a layer from PostGIS."""
        uri.setDataSource(schema, table, geometry_column)
        
        layer = QgsVectorLayer(uri.uri(), table, "postgres")
        
        if not layer.isValid():
            raise Exception(f"Failed to load layer: {table}")
        
        return layer

    def populate_input_layers(self):
        """Populate combo boxes with available layers in QGIS."""
        # Clear combo boxes before populating them
        self.dlg.combo_population_layer.clear()
        self.dlg.combo_school_layer.clear()
        self.dlg.combo_river_layer.clear()
        self.dlg.combo_district_layer.clear()

        # Populate combo boxes with layers available in QGIS
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):  # Ensure it's a vector layer
                self.dlg.combo_population_layer.addItem(layer.name())
                self.dlg.combo_school_layer.addItem(layer.name())
                self.dlg.combo_river_layer.addItem(layer.name())
                self.dlg.combo_district_layer.addItem(layer.name())

    def run_analysis(self):
        """Runs the school suitability analysis."""
        feedback = QgsProcessingFeedback()

        try:
            # Connect to the PostGIS database
            uri = QgsDataSourceUri()

            # Correct connection setup without keyword arguments
            uri.setConnection(
                self.db_params['host'],        # Host
                self.db_params['port'],        # Port
                self.db_params['database'],    # Database name
                self.db_params['user'],        # User
                self.db_params['password']     # Password
            )

            # Load layers from the database
            district_layer = self.load_layer_from_postgis(uri, "public", "districts", "geom")
            population_layer = self.load_layer_from_postgis(uri, "public", "population", "geom")
            school_layer = self.load_layer_from_postgis(uri, "public", "schools", "geom")
            rivers_layer = self.load_layer_from_postgis(uri, "public", "rivers", "geom")

            # Get user input for district and distances
            selected_district = self.dlg.combo_district_layer.currentText()

            # Get user-defined distance values
            school_distance = float(self.dlg.spin_distance_from_schools.text())  # Distance to existing schools in meters
            river_distance = float(self.dlg.spin_river_distance_buffer.text())  # Distance to rivers in meters

            # Step 1: Extract the selected district
            district = processing.run("native:extractbyattribute", {
                'INPUT': district_layer,
                'FIELD': 'name',  # Replace with the district name field
                'OPERATOR': '=',
                'VALUE': selected_district,
                'OUTPUT': 'memory:selected_district'
            }, feedback=feedback)['OUTPUT']

            # Step 2: Clip population data to the selected district
            clipped_population = processing.run("native:clip", {
                'INPUT': population_layer,
                'OVERLAY': district,
                'OUTPUT': 'memory:clipped_population'
            }, feedback=feedback)['OUTPUT']

            # Step 3: Filter areas with population > user-defined threshold (e.g., 1000)
            high_population_threshold = 1000  # This can be adjusted or made dynamic based on user input.
            high_population = processing.run("native:extractbyattribute", {
                'INPUT': clipped_population,
                'FIELD': 'population',  # Adjust field name based on your table
                'OPERATOR': '>=',
                'VALUE': high_population_threshold,
                'OUTPUT': 'memory:high_population'
            }, feedback=feedback)['OUTPUT']

            # Step 4: Buffer existing schools by user-defined distance
            school_buffer = processing.run("native:buffer", {
                'INPUT': school_layer,
                'DISTANCE': school_distance,
                'SEGMENTS': 5,
                'DISSOLVE': True,
                'OUTPUT': 'memory:school_buffer'
            }, feedback=feedback)['OUTPUT']

            # Step 5: Buffer rivers by user-defined distance
            river_buffer = processing.run("native:buffer", {
                'INPUT': rivers_layer,
                'DISTANCE': river_distance,
                'SEGMENTS': 5,
                'DISSOLVE': True,
                'OUTPUT': 'memory:river_buffer'
            }, feedback=feedback)['OUTPUT']

            # Step 6: Merge school and river buffers
            combined_buffer = processing.run("native:mergevectorlayers", {
                'LAYERS': [school_buffer, river_buffer],
                'OUTPUT': 'memory:combined_buffer'
            }, feedback=feedback)['OUTPUT']

            # Step 7: Remove unsuitable areas (areas with high population within buffers)
            suitable_areas = processing.run("native:difference", {
                'INPUT': high_population,
                'OVERLAY': combined_buffer,
                'OUTPUT': 'memory:suitable_areas'
            }, feedback=feedback)['OUTPUT']

            # Step 8: Clip suitable areas to district boundary
            final_suitable_areas = processing.run("native:clip", {
                'INPUT': suitable_areas,
                'OVERLAY': district,
                'OUTPUT': 'memory:final_suitable_areas'
            }, feedback=feedback)['OUTPUT']

            # Add the final suitable areas to QGIS
            suitable_layer = QgsVectorLayer(final_suitable_areas, "Suitable Areas", "memory")
            QgsProject.instance().addMapLayer(suitable_layer)

            QMessageBox.information(self.dlg, "Analysis Complete", "Suitable areas for schools identified.")

        except Exception as e:
            QMessageBox.critical(self.dlg, "Error", f"An error occurred: {str(e)}")
