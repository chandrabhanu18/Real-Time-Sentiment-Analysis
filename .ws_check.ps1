$ErrorActionPreference = 'Stop'
$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$uri = 'ws://localhost:8000/ws/sentiment'
$cts = New-Object System.Threading.CancellationTokenSource(10000)
try {
    $ws.ConnectAsync([System.Uri] $uri, $cts.Token).Wait()
    Write-Output "CONNECTED"
    $buffer = New-Object byte[] 4096
    $segment = New-Object System.ArraySegment[byte] ($buffer, 0, $buffer.Length)
    while (-not $cts.IsCancellationRequested) {
        $t = $ws.ReceiveAsync($segment, $cts.Token)
        $t.Wait()
        $res = $t.Result
        if ($res.Count -gt 0) {
            $msg = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $res.Count)
            Write-Output "MSG: $msg"
        }
        if ($res.CloseStatus -ne $null) { break }
    }
} catch {
    Write-Output "ERROR: $_"
} finally {
    $ws.Dispose()
}
