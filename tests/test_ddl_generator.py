import sys
import os
import unittest
import logging
import json
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from converters.ddl_generator import DDLGenerator

class TestDDLGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Suppress warnings from datatype_converter during tests
        logging.getLogger('converters.datatype_converter').setLevel(logging.CRITICAL)
        cls.logger = logging.getLogger(__name__)

    def test_ddl_generation(self):
        generator = DDLGenerator()
        
        # Mock JSON data with constraints
        mock_schema = [
            {
                "table_name": "USERS",
                "columns": [
                    {"name": "ID", "datatype": "NUMBER", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "USERNAME", "datatype": "VARCHAR2", "precision": 50, "scale": None, "nullable": False},
                    {"name": "CREATED_AT", "datatype": "DATE", "precision": None, "scale": None, "nullable": True}
                ],
                "constraints": [
                    {
                        "name": "PK_USERS",
                        "type": "P",
                        "columns": ["ID"],
                        "r_constraint_name": None
                    },
                    {
                        "name": "UQ_USERNAME",
                        "type": "U",
                        "columns": ["USERNAME"],
                        "r_constraint_name": None
                    }
                ]
            },
            {
                "table_name": "ORDERS",
                "columns": [
                    {"name": "ORDER_ID", "datatype": "NUMBER", "precision": None, "scale": None, "nullable": False},
                    {"name": "USER_ID", "datatype": "NUMBER", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "TOTAL_AMOUNT", "datatype": "NUMBER", "precision": 12, "scale": 2, "nullable": True}
                ],
                "constraints": [
                    {
                        "name": "PK_ORDERS",
                        "type": "P",
                        "columns": ["ORDER_ID"],
                        "r_constraint_name": None
                    },
                    {
                        "name": "FK_ORDERS_USER",
                        "type": "R",
                        "columns": ["USER_ID"],
                        "r_constraint_name": "PK_USERS"
                    }
                ]
            }
        ]
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w', encoding='utf-8') as tmp_json:
            json.dump(mock_schema, tmp_json)
            json_path = tmp_json.name
            
        output_dir = tempfile.mkdtemp()
            
        try:
            # Generate DDL
            count = generator.generate_ddl(json_path, output_dir)
            self.assertEqual(count, 2)
            
            # Verify USERS table SQL
            users_sql_path = os.path.join(output_dir, "tables", "USERS.sql")
            self.assertTrue(os.path.exists(users_sql_path))
            with open(users_sql_path, 'r', encoding='utf-8') as f:
                users_sql = f.read()
                
            self.assertIn('CREATE TABLE "USERS" (', users_sql)
            self.assertIn('"ID" BIGINT NOT NULL', users_sql)
            self.assertIn('CONSTRAINT "PK_USERS" PRIMARY KEY ("ID")', users_sql)
            self.assertIn('CONSTRAINT "UQ_USERNAME" UNIQUE ("USERNAME")', users_sql)
            
            # Verify ORDERS table SQL
            orders_sql_path = os.path.join(output_dir, "tables", "ORDERS.sql")
            self.assertTrue(os.path.exists(orders_sql_path))
            with open(orders_sql_path, 'r', encoding='utf-8') as f:
                orders_sql = f.read()
                
            self.assertIn('CREATE TABLE "ORDERS" (', orders_sql)
            self.assertIn('"ORDER_ID" NUMERIC NOT NULL', orders_sql)
            self.assertIn('CONSTRAINT "PK_ORDERS" PRIMARY KEY ("ORDER_ID")', orders_sql)
            
            # Verify constraints SQL
            constraints_sql_path = os.path.join(output_dir, "constraints.sql")
            self.assertTrue(os.path.exists(constraints_sql_path))
            with open(constraints_sql_path, 'r', encoding='utf-8') as f:
                constraints_sql = f.read()
                
            self.assertIn('ALTER TABLE "ORDERS"', constraints_sql)
            self.assertIn('ADD CONSTRAINT "FK_ORDERS_USER" FOREIGN KEY ("USER_ID")', constraints_sql)
            self.assertIn('REFERENCES "USERS" ("ID")', constraints_sql)
            
            self.logger.info("DDL Generator output verified successfully.")
            
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)

if __name__ == "__main__":
    unittest.main()
