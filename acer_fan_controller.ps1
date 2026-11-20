param(
    [ValidateSet("max", "auto", "cool", "manual", "query", "diag")]
    [string]$Mode = "max",
    [int]$CpuPct = 100,
    [int]$GpuPct = 100
)

$ErrorActionPreference = "Stop"

function Get-AcerGamingInstance {
    $useCim = $true
    $inst = $null
    try {
        $inst = Get-CimInstance -Namespace "root\wmi" -ClassName "AcerGamingFunction" -ErrorAction Stop | Select-Object -First 1
    } catch {
        $inst = $null
    }
    if (-not $inst) {
        $useCim = $false
        try {
            $inst = Get-WmiObject -Namespace "root\wmi" -Class "AcerGamingFunction" -ErrorAction Stop | Select-Object -First 1
        } catch {
            $inst = $null
        }
    }
    return @{ Instance = $inst; UseCim = $useCim }
}

function Invoke-AcerWmiMethod {
    param(
        [hashtable]$Target,
        [string]$MethodName,
        $ArgValue
    )
    $inst = $Target.Instance
    if ($Target.UseCim) {
        $res = Invoke-CimMethod -InputObject $inst -MethodName $MethodName -Arguments @{ gmInput = $ArgValue } -ErrorAction Stop
        if ($null -ne $res -and $null -ne $res.gmOutput) {
            return [uint64]$res.gmOutput
        }
        return [uint64]0
    } else {
        $inP = $inst.GetMethodParameters($MethodName)
        $inP["gmInput"] = $ArgValue
        $outP = $inst.InvokeMethod($MethodName, $inP, $null)
        if ($null -ne $outP -and $null -ne $outP["gmOutput"]) {
            return [uint64]$outP["gmOutput"]
        }
        return [uint64]0
    }
}

# lee un sensor probando el formato nuevo (0x02, nitro y predator recientes) y el antiguo (0x01)
function Read-AcerSensor {
    param([hashtable]$Target, [int]$SensorId, [int]$Max)
    foreach ($cmd in 0x02, 0x01) {
        try {
            $raw = Invoke-AcerWmiMethod -Target $Target -MethodName "GetGamingSysInfo" -ArgValue ([uint32](($SensorId -shl 8) -bor $cmd))
            if (($raw -band 0xFF) -eq 0) {
                $val = [int](($raw -shr 8) -band 0xFFFF)
                if ($val -gt 0 -and $val -le $Max) { return $val }
            }
        } catch {}
    }
    return 0
}

if ($Mode.ToLower() -eq "diag") {
    # informe para ajustar el soporte de modelos que no responden
    $info = [ordered]@{}
    try {
        $cs = Get-CimInstance Win32_ComputerSystem
        $info["modelo"] = "$($cs.Manufacturer) $($cs.Model)"
        $info["bios"] = (Get-CimInstance Win32_BIOS).SMBIOSBIOSVersion
    } catch {}
    try {
        $info["clases_wmi"] = @(Get-CimClass -Namespace "root\wmi" -ErrorAction Stop | Where-Object { $_.CimClassName -match '^Acer|Gaming|Predator|Nitro' } | ForEach-Object { $_.CimClassName })
    } catch { $info["clases_wmi"] = "error: $($_.Exception.Message)" }
    $t = Get-AcerGamingInstance
    $info["acer_gaming_function"] = [bool]$t.Instance
    if ($t.Instance) {
        try { $info["metodos"] = @((Get-CimClass -Namespace "root\wmi" -ClassName "AcerGamingFunction").CimClassMethods | ForEach-Object { $_.Name }) } catch {}
        $raw = [ordered]@{}
        foreach ($inp in 0x0101, 0x0102, 0x0201, 0x0202, 0x0601, 0x0602, 0x0A01, 0x0A02) {
            $key = "0x{0:X4}" -f $inp
            try { $raw[$key] = "0x{0:X}" -f (Invoke-AcerWmiMethod -Target $t -MethodName "GetGamingSysInfo" -ArgValue ([uint32]$inp)) }
            catch { $raw[$key] = "error: $($_.Exception.Message)" }
        }
        $info["GetGamingSysInfo"] = $raw
        foreach ($m in "GetGamingFanBehavior", "GetGamingFanSpeed") {
            foreach ($inp in 0x01, 0x04) {
                $key = "{0}(0x{1:X2})" -f $m, $inp
                try { $info[$key] = "0x{0:X}" -f (Invoke-AcerWmiMethod -Target $t -MethodName $m -ArgValue ([uint32]$inp)) }
                catch { $info[$key] = "error: $($_.Exception.Message)" }
            }
        }
    }
    $info | ConvertTo-Json -Depth 4
    exit 0
}

try {
    $target = Get-AcerGamingInstance
    if (-not $target.Instance) {
        Write-Output "NO_WMI: AcerGamingFunction no disponible"
        exit 2
    }

    switch ($Mode.ToLower()) {
        "max" {
            $ok = $false
            try {
                $rc = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanBehavior" -ArgValue ([uint64]0x820009)
                if (($rc -band 0xFF) -eq 0) { $ok = $true }
            } catch {}

            if (-not $ok) {
                # Respaldo: modo manual (0xC30009) + 100% en ventilador CPU (0x01) y GPU (0x04)
                $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanBehavior" -ArgValue ([uint64]0xC30009)
                $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanSpeed" -ArgValue ([uint64]0x6401)
                $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanSpeed" -ArgValue ([uint64]0x6404)
            }
            Write-Output "OK: ACER_FAN_MAX"
        }
        { $_ -in @("auto", "cool") } {
            $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanBehavior" -ArgValue ([uint64]0x410009)
            Write-Output "OK: ACER_FAN_AUTO"
        }
        "manual" {
            $c = [math]::Max(0, [math]::Min(100, $CpuPct))
            $g = [math]::Max(0, [math]::Min(100, $GpuPct))
            $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanBehavior" -ArgValue ([uint64]0xC30009)
            $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanSpeed" -ArgValue ([uint64](($c -shl 8) -bor 0x01))
            $null = Invoke-AcerWmiMethod -Target $target -MethodName "SetGamingFanSpeed" -ArgValue ([uint64](($g -shl 8) -bor 0x04))
            Write-Output "OK: ACER_FAN_MANUAL CPU=$c GPU=$g"
        }
        "query" {
            # sensores 0x01 temperatura cpu, 0x02 ventilador cpu, 0x06 ventilador gpu
            $cpuTemp = Read-AcerSensor -Target $target -SensorId 0x01 -Max 115
            $rpm1 = Read-AcerSensor -Target $target -SensorId 0x02 -Max 12000
            $rpm2 = Read-AcerSensor -Target $target -SensorId 0x06 -Max 12000
            Write-Output "CPU_TEMP=$cpuTemp|FAN1_RPM=$rpm1|FAN2_RPM=$rpm2"
        }
    }
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
