import sys
import os
import unittest
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from converters.datatype_converter import DatatypeConverter

class TestDatatypeConverter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We don't want to clutter test output with warning logs, 
        # but we need to ensure they don't throw exceptions.
        logging.getLogger('converters.datatype_converter').setLevel(logging.CRITICAL)
        logging.getLogger('validators.type_validator').setLevel(logging.CRITICAL)
        
        cls.converter = DatatypeConverter()

    def test_basic_mappings(self):
        self.assertEqual(self.converter.convert_type("VARCHAR2", 50), "VARCHAR(50)")
        self.assertEqual(self.converter.convert_type("DATE"), "TIMESTAMP")
        self.assertEqual(self.converter.convert_type("CLOB"), "TEXT")
        self.assertEqual(self.converter.convert_type("BLOB"), "BYTEA")

    def test_number_mappings(self):
        # Unscaled number
        self.assertEqual(self.converter.convert_type("NUMBER"), "NUMERIC")
        # Scaled number (precision and scale)
        self.assertEqual(self.converter.convert_type("NUMBER", 10, 2), "NUMERIC(10, 2)")
        # Number mapped to smallint (scale 0, precision <= 4)
        self.assertEqual(self.converter.convert_type("NUMBER", 3, 0), "SMALLINT")
        # Number mapped to integer (scale 0, precision <= 9)
        self.assertEqual(self.converter.convert_type("NUMBER", 8, 0), "INTEGER")
        # Number mapped to bigint (scale 0, precision <= 18)
        self.assertEqual(self.converter.convert_type("NUMBER", 15, 0), "BIGINT")
        # Number mapped to numeric (scale 0, precision > 18)
        self.assertEqual(self.converter.convert_type("NUMBER", 38, 0), "NUMERIC(38, 0)")

    def test_fallback_mapping(self):
        # UNKNOWN_TYPE should fallback to TEXT
        with self.assertLogs('converters.datatype_converter', level='WARNING') as cm:
            logging.getLogger('converters.datatype_converter').setLevel(logging.WARNING)
            result = self.converter.convert_type("UNKNOWN_TYPE")
            self.assertEqual(result, "TEXT")
            self.assertTrue(any("Risky Conversion: Unknown Oracle type" in log for log in cm.output))
        logging.getLogger('converters.datatype_converter').setLevel(logging.CRITICAL)

    def test_risky_conversions_logs(self):
        # DATE to TIMESTAMP warning
        with self.assertLogs('converters.datatype_converter', level='WARNING') as cm:
            logging.getLogger('converters.datatype_converter').setLevel(logging.WARNING)
            self.converter.convert_type("DATE")
            self.assertTrue(any("Oracle 'DATE' includes time" in log for log in cm.output))
            
            # NUMBER without precision warning
            self.converter.convert_type("NUMBER")
            self.assertTrue(any("Oracle 'NUMBER' without precision" in log for log in cm.output))
        logging.getLogger('converters.datatype_converter').setLevel(logging.CRITICAL)

if __name__ == "__main__":
    unittest.main()
