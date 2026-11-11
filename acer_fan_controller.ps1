param(
    [ValidateSet("max", "auto", "cool", "manual", "query")]
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
            $cpuTemp = 0
            $rpm1 = 0
            $rpm2 = 0
            try {
                $tRaw = Invoke-AcerWmiMethod -Target $target -MethodName "GetGamingSysInfo" -ArgValue ([uint32]0x0101)
                if (($tRaw -band 0xFF) -eq 0) {
                    $tVal = [int](($tRaw -shr 8) -band 0xFFFF)
                    if ($tVal -gt 0 -and $tVal -le 115) { $cpuTemp = $tVal }
                }
            } catch {}
            try {
                $f1Raw = Invoke-AcerWmiMethod -Target $target -MethodName "GetGamingSysInfo" -ArgValue ([uint32]0x0201)
                if (($f1Raw -band 0xFF) -eq 0) {
                    $f1Val = [int](($f1Raw -shr 8) -band 0xFFFF)
                    if ($f1Val -ge 0 -and $f1Val -le 12000) { $rpm1 = $f1Val }
                }
            } catch {}
            try {
                $f2Raw = Invoke-AcerWmiMethod -Target $target -MethodName "GetGamingSysInfo" -ArgValue ([uint32]0x0601)
                if (($f2Raw -band 0xFF) -eq 0) {
                    $f2Val = [int](($f2Raw -shr 8) -band 0xFFFF)
                    if ($f2Val -ge 0 -and $f2Val -le 12000) { $rpm2 = $f2Val }
                }
            } catch {}
            Write-Output "CPU_TEMP=$cpuTemp|FAN1_RPM=$rpm1|FAN2_RPM=$rpm2"
        }
    }
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
