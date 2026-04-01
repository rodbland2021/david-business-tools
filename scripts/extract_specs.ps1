# David Business Tools — Laptop Spec Extraction Script
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
