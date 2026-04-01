import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
from specs_tools import _parse_script_output

DELL_LATITUDE_JSON = json.dumps({
    "ComputerName": "DESKTOP-ABC123",
    "Manufacturer": "Dell Inc.",
    "Model": "Latitude 5540",
    "SerialNumber": "ABC1234XYZ",
    "CPU": "Intel(R) Core(TM) i7-1365U @ 1.80GHz",
    "CPUCores": 12,
    "TotalRAM_GB": 16,
    "RAMType": "DDR4",
    "RAMSpeed_MHz": 3200,
    "GPU": "Intel Iris Xe Graphics",
    "GPU_VRAM_MB": 1024,
    "Disks": [
        {
            "Model": "Samsung MZNLN512HAJQ-000H1",
            "Size_GB": 512,
            "SerialNumber": "SN12345678",
            "MediaType": "SSD"
        }
    ],
    "BatteryHealth_Percent": 92,
    "ScreenResolution": "Check display settings",
    "WindowsProductKey": "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",
    "OS": "Windows 11 Pro"
})


def test_parse_valid_output():
    result = _parse_script_output(DELL_LATITUDE_JSON)
    assert result.get("brand") == "Dell"
    assert result.get("model") == "Latitude 5540"
    assert "i7" in result["specs"]["cpu"]["model"]
    assert result["specs"]["ram"]["total_gb"] == 16
    assert result["specs"]["storage"][0]["capacity_gb"] == 512
    assert result.get("serial_number")


def test_parse_invalid_json():
    result = _parse_script_output("not json at all")
    assert "error" in result
