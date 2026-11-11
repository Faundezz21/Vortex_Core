param(
    [ValidateSet("lenovo", "asus", "dell")]
    [string]$Brand,
    [ValidateSet("max", "auto", "cool", "query")]
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"

function Get-SafeCimFirst($ns, $cls) {
    try {
        return Get-CimInstance -Namespace $ns -ClassName $cls -ErrorAction Stop | Select-Object -First 1
    } catch {
        try {
            return Get-WmiObject -Namespace $ns -Class $cls -ErrorAction Stop | Select-Object -First 1
        } catch {
            return $null
        }
    }
}

try {
    switch ($Brand.ToLower()) {
        "lenovo" {
            $inst = Get-SafeCimFirst "root\wmi" "LENOVO_GAMEZONE_DATA"
            if (-not $inst) {
                Write-Output "NO_WMI: LENOVO_GAMEZONE_DATA no disponible"
                exit 2
            }
            if ($Mode -eq "query") {
                $mVal = 0
                try {
                    if ($inst -is [Microsoft.Management.Infrastructure.CimInstance]) {
                        $r = Invoke-CimMethod -InputObject $inst -MethodName "GetSmartFanMode" -ErrorAction Stop
                        if ($null -ne $r.Data) { $mVal = [int]$r.Data }
                    } else {
                        $r = $inst.InvokeMethod("GetSmartFanMode", $null, $null)
                        if ($null -ne $r -and $null -ne $r["Data"]) { $mVal = [int]$r["Data"] }
                    }
                } catch {}
                Write-Output "SMART_FAN_MODE=$mVal|CPU_TEMP=0|FAN1_RPM=0|FAN2_RPM=0"
                exit 0
            }
            # 1 = Quiet/Cool, 2 = Balanced/Auto, 3 = Performance/Max
            $val = switch ($Mode.ToLower()) {
                "max"  { [uint32]3 }
                "cool" { [uint32]1 }
                default { [uint32]2 }
            }
            if ($inst -is [Microsoft.Management.Infrastructure.CimInstance]) {
                $null = Invoke-CimMethod -InputObject $inst -MethodName "SetSmartFanMode" -Arguments @{ Data = $val } -ErrorAction Stop
            } else {
                $inP = $inst.GetMethodParameters("SetSmartFanMode")
                $inP["Data"] = $val
                $null = $inst.InvokeMethod("SetSmartFanMode", $inP, $null)
            }
            Write-Output "OK: LENOVO_SMART_FAN=$val"
        }

        "asus" {
            $inst = Get-SafeCimFirst "root\wmi" "AsusAtkWmi_WMNB"
            if (-not $inst) {
                Write-Output "NO_WMI: AsusAtkWmi_WMNB no disponible"
                exit 2
            }
            if ($Mode -eq "query") {
                $rpm1 = 0
                $rpm2 = 0
                foreach ($pair in @(@(0x00110013, "cpu"), @(0x00110014, "gpu"))) {
                    try {
                        $devId = [uint32]$pair[0]
                        $raw = 0
                        if ($inst -is [Microsoft.Management.Infrastructure.CimInstance]) {
                            $r = Invoke-CimMethod -InputObject $inst -MethodName "DSTS" -Arguments @{ Device_ID = $devId } -ErrorAction Stop
                            if ($null -ne $r.device_status) { $raw = [uint32]$r.device_status }
                        } else {
                            $inP = $inst.GetMethodParameters("DSTS")
                            $inP["Device_ID"] = $devId
                            $r = $inst.InvokeMethod("DSTS", $inP, $null)
                            if ($null -ne $r -and $null -ne $r["device_status"]) { $raw = [uint32]$r["device_status"] }
                        }
                        if ($raw -gt 0x10000) {
                            $v = [int]($raw -band 0xFFFF)
                            if ($v -gt 0 -and $v -lt 150) { $v = $v * 100 }
                            if ($v -ge 200 -and $v -le 12000) {
                                if ($pair[1] -eq "cpu") { $rpm1 = $v } else { $rpm2 = $v }
                            }
                        }
                    } catch {}
                }
                Write-Output "CPU_TEMP=0|FAN1_RPM=$rpm1|FAN2_RPM=$rpm2"
                exit 0
            }
            # Device_ID 0x00120075: ThrottleThermalPolicy (0 = Balanced, 1 = Turbo, 2 = Silent)
            $ctrl = switch ($Mode.ToLower()) {
                "max"  { [uint32]1 }
                "cool" { [uint32]2 }
                default { [uint32]0 }
            }
            if ($inst -is [Microsoft.Management.Infrastructure.CimInstance]) {
                $null = Invoke-CimMethod -InputObject $inst -MethodName "DEVS" -Arguments @{ Device_ID = [uint32]0x00120075; Control_status = $ctrl } -ErrorAction Stop
            } else {
                $inP = $inst.GetMethodParameters("DEVS")
                $inP["Device_ID"] = [uint32]0x00120075
                $inP["Control_status"] = $ctrl
                $null = $inst.InvokeMethod("DEVS", $inP, $null)
            }
            Write-Output "OK: ASUS_THERMAL_POLICY=$ctrl"
        }

        "dell" {
            $inst = Get-SafeCimFirst "root\wmi" "AWCCWmiMethodFunction"
            if (-not $inst) {
                Write-Output "NO_WMI: AWCCWmiMethodFunction no disponible"
                exit 2
            }
            if ($Mode -eq "query") {
                # Muchas placas Dell/Alienware no exponen el ID exacto universal sin consultar tabla; reportamos solo si responde sin fallo
                Write-Output "CPU_TEMP=0|FAN1_RPM=0|FAN2_RPM=0"
                exit 0
            }
            # Thermal_Control: command 0x01 + mode byte (0xAB = G-Mode/Max, 0xA0 = Balanced)
            $arg2 = if ($Mode.ToLower() -eq "max") { [uint32]0x0000AB01 } else { [uint32]0x0000A001 }
            if ($inst -is [Microsoft.Management.Infrastructure.CimInstance]) {
                $null = Invoke-CimMethod -InputObject $inst -MethodName "Thermal_Control" -Arguments @{ arg2 = $arg2 } -ErrorAction Stop
            } else {
                $inP = $inst.GetMethodParameters("Thermal_Control")
                $inP["arg2"] = $arg2
                $null = $inst.InvokeMethod("Thermal_Control", $inP, $null)
            }
            Write-Output "OK: DELL_AWCC=$arg2"
        }
    }
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
