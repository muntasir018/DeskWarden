# DeskWarden -- Python installer downloader with inline progress bar
param([string]$Dest)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Find latest Python amd64 URL
try {
    $ProgressPreference = 'SilentlyContinue'
    $req = Invoke-WebRequest -Uri 'https://www.python.org/downloads/windows/' -UseBasicParsing
    $url = ($req.Links | Where-Object { $_.href -match 'amd64\.exe$' } | Select-Object -First 1).href
} catch {
    Write-Host "  [ERROR] Could not reach python.org: $_"
    exit 1
}
if (-not $url) { Write-Host "  [ERROR] No installer URL found."; exit 1 }

$fname = $url.Split('/')[-1]
Write-Host "  $fname"

# Chunked download
$CHUNK  = 65536
$done   = 0
$total  = 0
$speeds = [System.Collections.Generic.List[double]]::new()
$lastT  = [DateTime]::UtcNow
$lastD  = 0
$start  = [DateTime]::UtcNow
$BAR    = 34

try {
    $req2   = [Net.HttpWebRequest]::Create($url)
    $req2.Timeout = 120000
    $resp   = $req2.GetResponse()
    $total  = $resp.ContentLength
    $stream = $resp.GetResponseStream()
    $fs     = [IO.File]::Create($Dest)
    $buf    = New-Object byte[] $CHUNK

    while ($true) {
        $read = $stream.Read($buf, 0, $CHUNK)
        if ($read -le 0) { break }
        $fs.Write($buf, 0, $read)
        $done += $read

        $now = [DateTime]::UtcNow
        $dt  = ($now - $lastT).TotalSeconds
        if ($dt -ge 0.15) {
            $inst = ($done - $lastD) / $dt
            $speeds.Add($inst)
            if ($speeds.Count -gt 6) { $speeds.RemoveAt(0) }
            $bps  = ($speeds | Measure-Object -Sum).Sum / $speeds.Count
            $pct  = if ($total -gt 0) { [int]($done*100/$total) } else { [Math]::Min(97,[int]($done/1000000)) }
            $eta  = if ($bps -gt 0 -and $total -gt $done) { ($total-$done)/$bps } else { 0 }

            $filled = [string][char]0x2588 * [int]($BAR*$pct/100)
            $empty  = [string][char]0x2591 * ($BAR - [int]($BAR*$pct/100))
            $mb     = "{0:F1}" -f ($done/1MB)
            $tmb    = "{0:F1}" -f ($total/1MB)
            $spd    = if ($bps -lt 1MB) { "{0:F0} KB/s" -f ($bps/1KB) } else { "{0:F1} MB/s" -f ($bps/1MB) }
            $eta_s  = if ($eta -gt 1) { "ETA {0:F0}s" -f $eta } else { "      " }
            $line   = "  " + $filled + $empty + ("  {0,3}%  {1} MB / {2} MB  {3}  {4}  " -f $pct,$mb,$tmb,$spd,$eta_s)

            [Console]::Write("`r" + $line)
            $lastT = $now
            $lastD = $done
        }
    }
    $fs.Close(); $stream.Close(); $resp.Close()
} catch {
    if ($fs) { $fs.Close() }
    [Console]::WriteLine("`r  [ERROR] $_                                        ")
    exit 1
}

$elapsed = ([DateTime]::UtcNow - $start).TotalSeconds
$avg     = if ($elapsed -gt 0) { $done/$elapsed } else { 0 }
$avgStr  = if ($avg -lt 1MB) { "{0:F0} KB/s" -f ($avg/1KB) } else { "{0:F1} MB/s" -f ($avg/1MB) }
$doneBar = [string][char]0x2588 * $BAR
[Console]::WriteLine("`r  " + $doneBar + ("  100%  {0:F1} MB  {1}  {2:F1}s          " -f ($done/1MB),$avgStr,$elapsed))

if (-not (Test-Path $Dest)) {
    Write-Host "  [ERROR] Download failed - file not found."
    exit 1
}
exit 0
