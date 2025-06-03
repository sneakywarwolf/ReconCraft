import unittest
import os
from reconcraft import read_ip_list, check_tool_installed

class TestReconCraftHelpers(unittest.TestCase):

    def test_read_ip_list_valid(self):
        test_file = "test_ips.txt"
        with open(test_file, "w") as f:
            f.write("192.168.1.1\nexample.com\n\n")
        result = read_ip_list(test_file)
        self.assertEqual(result, ["192.168.1.1", "example.com"])
        os.remove(test_file)

    def test_check_tool_installed(self):
        self.assertTrue(check_tool_installed("python"))
        self.assertFalse(check_tool_installed("nonexistent_tool_xyz"))

if __name__ == '__main__':
    unittest.main()