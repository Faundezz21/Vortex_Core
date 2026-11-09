param(
    [ValidateSet("max", "auto", "cool", "performance", "status", "query")]
    [string]$Mode = "max"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Management

function Invoke-HpBios {
    param(
        [uint32]$CommandType,
        [byte[]]$Data,
        [int]$OutSize = 4,
        [uint32]$Command = 0x20008
    )

    $searcher = New-Object System.Management.ManagementObjectSearcher("root\wmi", "SELECT * FROM hpqBIntM")
    $enum = $searcher.Get().GetEnumerator()
    if (-not $enum.MoveNext()) {
        throw "Acceso denegado a hpqBIntM (Ejecuta como Administrador)"
    }
    $intf = $enum.Current

    $cls = New-Object System.Management.ManagementClass("root\wmi", "hpqBDataIn", $null)
    $din = $cls.CreateInstance()
    $din["Sign"] = [byte[]]@(0x53, 0x45, 0x43, 0x55) # "SECU" magic bytes de HP
    $din["Command"] = $Command
    $din["CommandType"] = $CommandType
    $din["Size"] = [uint32]$Data.Length
    $din["hpqBData"] = $Data

    $method = "hpqBIOSInt$OutSize"
    $inP = $intf.GetMethodParameters($method)
    $inP["InData"] = $din

    $outP = $intf.InvokeMethod($method, $inP, $null)
    $outD = $outP["OutData"]
    $rc = [uint32]$outD["rwReturnCode"]
    
    return @{
        ReturnCode = $rc
        Data = $outD["Data"]
    }
}

try {
    switch ($Mode.ToLower()) {
        "max" {
            # 0x27: Max Fan Mode (1 = ON / Forzar 100% Turbina)
            $null = Invoke-HpBios -CommandType 0x27 -Data ([byte[]]@(0x01)) -OutSize 4
            # 0x1A: Perfil Performance (0x31)
            $null = Invoke-HpBios -CommandType 0x1A -Data ([byte[]]@(0xFF, 0x31, 0x00, 0x00)) -OutSize 4
            Write-Output "OK: FAN_MAX_ACTIVATED (Turbina 100% OMEN)"
        }
        "auto" {
            # 0x27: Max Fan Mode (0 = OFF / Curva Normal)
            $null = Invoke-HpBios -CommandType 0x27 -Data ([byte[]]@(0x00)) -OutSize 4
            # 0x1A: Perfil Default (0x30)
            $null = Invoke-HpBios -CommandType 0x1A -Data ([byte[]]@(0xFF, 0x30, 0x00, 0x00)) -OutSize 4
            Write-Output "OK: FAN_AUTO_DEFAULT"
        }
        "cool" {
            # 0x27: Max Fan Mode (0 = OFF)
            $null = Invoke-HpBios -CommandType 0x27 -Data ([byte[]]@(0x00)) -OutSize 4
            # 0x1A: Perfil Cool (0x50)
            $null = Invoke-HpBios -CommandType 0x1A -Data ([byte[]]@(0xFF, 0x50, 0x00, 0x00)) -OutSize 4
            Write-Output "OK: FAN_COOL_MODE"
        }
        "query" {
            # 1. Lectura de RPM de ventiladores (Opcode 0x2D -> Buffer 128 bytes)
            $rpm1 = 0
            $rpm2 = 0
            try {
                $f = Invoke-HpBios -CommandType 0x2D -Data ([byte[]]@(0,0,0,0)) -OutSize 128
                if ($f.ReturnCode -eq 0 -and $f.Data -and $f.Data.Length -ge 2) {
                    $rpm1 = [int]$f.Data[0] * 100
                    $rpm2 = [int]$f.Data[1] * 100
                }
            } catch {}

            # 2. Lectura térmica de CPU (Opcode 0x23 -> Buffer 4 bytes)
            $cpuTemp = 0
            try {
                $t = Invoke-HpBios -CommandType 0x23 -Data ([byte[]]@(0,0,0,0)) -OutSize 4
                if ($t.ReturnCode -eq 0 -and $t.Data -and $t.Data.Length -ge 1) {
                    $cpuTemp = [int]$t.Data[0]
                }
            } catch {}

            # Fallback de temperatura si la BIOS no la entregó por 0x23
            if ($cpuTemp -eq 0 -or $cpuTemp -gt 115) {
                try {
                    $tz = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1
                    if ($tz -and $tz.CurrentTemperature -gt 2732) {
                        $cpuTemp = [int](($tz.CurrentTemperature - 2732) / 10)
                    }
                } catch {}
            }

            Write-Output "CPU_TEMP=$cpuTemp|FAN1_RPM=$rpm1|FAN2_RPM=$rpm2"
        }
    }
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
}
