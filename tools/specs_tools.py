import json

POWERSHELL_SCRIPT = r"""# David Business Tools — Laptop Spec Extraction Script
# Run: Right-click > Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File extract_specs.ps1
$ErrorActionPreference = 'SilentlyContinue'
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ram = Get-CimInstance Win32_PhysicalMemory
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
$disks = Get-CimInstance Win32_DiskDrive | ForEach-Object {
    [PSCustomObject]@{
        Model = $_.Model
        Size_GB = [math]::Round($_.Size / 1GB)
        SerialNumber = $_.SerialNumber.Trim()
        MediaType = if ($_.MediaType -match 'SSD|Solid') { 'SSD' } elseif ($_.MediaType -match 'Fixed') { 'HDD' } else { $_.MediaType }
    }
}
$battery = Get-CimInstance Win32_Battery
$os = Get-CimInstance Win32_OperatingSystem
$key = (Get-CimInstance SoftwareLicensingService).OA3xOriginalProductKey
$totalRAM = ($ram | Measure-Object -Property Capacity -Sum).Sum / 1GB
$ramType = switch (($ram | Select-Object -First 1).SMBIOSMemoryType) { 26 { 'DDR4' }; 34 { 'DDR5' }; 24 { 'DDR3' }; default { 'Unknown' } }
$ramSpeed = ($ram | Select-Object -First 1).Speed
$batteryHealth = if ($battery) {
    $design = $battery.DesignCapacity; $full = $battery.FullChargeCapacity
    if ($design -and $full -and $design -gt 0) { [math]::Round(($full / $design) * 100) } else { 'Unknown' }
} else { 'No battery' }
$specs = [PSCustomObject]@{
    ComputerName = $cs.Name; Manufacturer = $cs.Manufacturer; Model = $cs.Model
    SerialNumber = $bios.SerialNumber.Trim(); CPU = $cpu.Name; CPUCores = $cpu.NumberOfLogicalProcessors
    TotalRAM_GB = [math]::Round($totalRAM); RAMType = $ramType; RAMSpeed_MHz = $ramSpeed
    GPU = $gpu.Name; GPU_VRAM_MB = [math]::Round($gpu.AdapterRAM / 1MB)
    Disks = @($disks); BatteryHealth_Percent = $batteryHealth
    ScreenResolution = "Check display settings"; WindowsProductKey = if ($key) { $key } else { 'Not found' }
    OS = $os.Caption
}
$specs | ConvertTo-Json -Depth 3
"""

_BRAND_MAP = {
    "Dell Inc.": "Dell",
    "Lenovo": "Lenovo",
    "HP": "HP",
    "Hewlett-Packard": "HP",
    "ASUS": "Asus",
    "Acer": "Acer",
    "Microsoft": "Microsoft",
    "Apple": "Apple",
    "Toshiba": "Toshiba",
    "Samsung": "Samsung",
    "MSI": "MSI",
    "Razer": "Razer",
    "LG": "LG",
}


def _parse_script_output(raw_json: str) -> dict:
    try:
        data = json.loads(raw_json)
    except Exception as e:
        return {"error": f"Failed to parse JSON: {e}"}

    manufacturer = data.get("Manufacturer", "")
    brand = manufacturer
    for key, mapped in _BRAND_MAP.items():
        if key.lower() in manufacturer.lower():
            brand = mapped
            break

    model = data.get("Model", "")

    cpu_model = data.get("CPU", "")
    cpu_cores = data.get("CPUCores", 0)

    gpu_model = data.get("GPU", "")
    gpu_vram_mb = data.get("GPU_VRAM_MB", 0)

    total_ram_gb = data.get("TotalRAM_GB", 0)
    ram_type = data.get("RAMType", "Unknown")
    ram_speed = data.get("RAMSpeed_MHz", 0)

    raw_disks = data.get("Disks", [])
    if isinstance(raw_disks, dict):
        raw_disks = [raw_disks]
    storage = []
    for disk in raw_disks:
        storage.append({
            "type": disk.get("MediaType", "Unknown"),
            "capacity_gb": disk.get("Size_GB", 0),
            "serial": disk.get("SerialNumber", ""),
            "model": disk.get("Model", ""),
        })

    battery_health = str(data.get("BatteryHealth_Percent", "Unknown"))
    resolution = data.get("ScreenResolution", "")
    serial_number = data.get("SerialNumber", "")
    windows_key = data.get("WindowsProductKey", "")
    os_name = data.get("OS", "")

    cpu_short = cpu_model
    if "@" in cpu_model:
        cpu_short = cpu_model.split("@")[0].strip()
    for prefix in ("Intel Core ", "Intel(R) Core(TM) ", "AMD Ryzen "):
        if cpu_short.startswith(prefix):
            cpu_short = cpu_short[len(prefix):]
            break

    storage_gb = storage[0]["capacity_gb"] if storage else 0
    storage_type = storage[0]["type"] if storage else "SSD"
    suggested_name = f"{brand} {model} - {cpu_short} / {total_ram_gb}GB / {storage_gb}GB {storage_type}"

    return {
        "brand": brand,
        "model": model,
        "serial_number": serial_number,
        "windows_key": windows_key,
        "os": os_name,
        "specs": {
            "cpu": {"model": cpu_model, "cores": cpu_cores},
            "gpu": {"model": gpu_model, "vram_mb": gpu_vram_mb},
            "ram": {"total_gb": total_ram_gb, "type": ram_type, "speed_mhz": ram_speed},
            "storage": storage,
            "battery_health": battery_health,
            "screen": {"resolution": resolution},
        },
        "suggested_name": suggested_name,
    }


def register(mcp):
    @mcp.tool
    def specs_generate_script() -> str:
        """Return the PowerShell script that extracts laptop hardware specs. David runs this on a Windows laptop and pastes the output back."""
        return POWERSHELL_SCRIPT

    @mcp.tool
    def specs_parse_script_output(raw_json: str) -> str:
        """Parse the JSON output from the PowerShell extract_specs script. Returns structured product data ready for store_add_product."""
        result = _parse_script_output(raw_json)
        return json.dumps(result)
